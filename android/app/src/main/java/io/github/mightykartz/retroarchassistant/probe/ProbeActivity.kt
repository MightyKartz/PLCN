package io.github.mightykartz.retroarchassistant.probe

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.DocumentsContract
import android.view.ViewGroup
import android.view.WindowInsets
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.widget.Button
import android.widget.LinearLayout
import androidx.webkit.WebViewAssetLoader
import androidx.webkit.WebViewClientCompat
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File
import java.util.concurrent.Executors
import org.json.JSONObject

class ProbeActivity : Activity() {
    private data class Preview(val document: Uri, val before: ByteArray, val after: ByteArray, val report: String)

    private val worker = Executors.newSingleThreadExecutor()
    private val prefs by lazy { getSharedPreferences("storage", MODE_PRIVATE) }
    private lateinit var page: WebView
    private lateinit var choose: Button
    private lateinit var inspect: Button
    private lateinit var apply: Button
    private var running = false
    private var pageReady = false
    private var message = ""
    private var preview: Preview? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        choose = Button(this).apply {
            text = "授权测试目录"
            setOnClickListener {
                startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT_TREE), PICK_TREE)
            }
        }
        inspect = Button(this).apply {
            text = "预览 RAA-Probe.lpl"
            setOnClickListener { inspectFixture() }
        }
        apply = Button(this).apply {
            text = "备份并写入测试列表"
            setOnClickListener { applyPreview() }
        }

        val loader = WebViewAssetLoader.Builder()
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(this))
            .build()
        page = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.allowFileAccess = false
            settings.allowContentAccess = false
            webViewClient = object : WebViewClientCompat() {
                override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest) =
                    loader.shouldInterceptRequest(request.url)

                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest) = true

                override fun onPageFinished(view: WebView, url: String) {
                    pageReady = true
                    refresh()
                }
            }
            loadUrl("https://appassets.androidplatform.net/assets/index.html")
        }
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(choose)
            addView(inspect)
            addView(apply)
            addView(page, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        }
        if (Build.VERSION.SDK_INT >= 35) {
            layout.setOnApplyWindowInsetsListener { view, insets ->
                val bars = insets.getInsets(WindowInsets.Type.systemBars())
                view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
                insets
            }
        }
        setContentView(layout)
        message = if (grantedTree() == null) "请选择放有测试列表的目录。" else "测试目录授权有效，可以预览。"
        refresh()
    }

    private fun grantedTree(): Uri? {
        val saved = prefs.getString("tree", null) ?: return null
        return contentResolver.persistedUriPermissions.firstOrNull {
            it.uri.toString() == saved && it.isReadPermission && it.isWritePermission
        }?.uri
    }

    @Deprecated("Uses the platform Activity picker without adding an Activity library")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != PICK_TREE || resultCode != RESULT_OK) return
        val tree = data?.data ?: return
        val previous = grantedTree()
        preview = null
        try {
            contentResolver.takePersistableUriPermission(tree, GRANT_FLAGS)
            prefs.edit().putString("tree", tree.toString()).apply()
            if (previous != null && previous != tree) {
                contentResolver.releasePersistableUriPermission(previous, GRANT_FLAGS)
            }
            message = "目录已授权，可以预览。"
        } catch (error: SecurityException) {
            message = "无法保留目录读写授权。\n${error.message}"
        }
        refresh()
    }

    private fun inspectFixture() {
        val tree = grantedTree() ?: return
        preview = null
        runOperation("读取和预览测试列表…") {
            val parent = DocumentsContract.getTreeDocumentId(tree)
            val children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, parent)
            val columns = arrayOf(DocumentsContract.Document.COLUMN_DOCUMENT_ID, DocumentsContract.Document.COLUMN_DISPLAY_NAME)
            val target = contentResolver.query(children, columns, null, null, null)?.use { rows ->
                var document: Uri? = null
                while (rows.moveToNext() && document == null) {
                    if (rows.getString(1) == FIXTURE) {
                        document = DocumentsContract.buildDocumentUriUsingTree(tree, rows.getString(0))
                    }
                }
                document
            } ?: error("授权目录内找不到 $FIXTURE")
            val before = read(target)
            val folder = File(cacheDir, "preview").apply { mkdirs() }
            val input = File(folder, "input.lpl").apply { writeBytes(before) }
            val output = File(folder, "output.lpl")
            if (!Python.isStarted()) Python.start(AndroidPlatform(this))
            val probe = Python.getInstance().getModule("probe")
            val dependencies = probe.callAttr("dependencies").toString()
            val result = JSONObject(probe.callAttr("preview", input.path, output.path).toString())
            val report = "依赖自检通过 · $dependencies\n\n" +
                "原名称 · ${result.getString("before")}\n新名称 · ${result.getString("after")}\n" +
                "RetroArch 启动路径 · ${result.getString("launchPath")}\n\n请退出 RetroArch 后再写入。"
            val pending = Preview(target, before, output.readBytes(), report)
            runOnUiThread {
                preview = pending
                message = pending.report
            }
        }
    }

    private fun applyPreview() {
        val pending = preview ?: return
        preview = null
        runOperation("备份和验证测试写入…") {
            check(read(pending.document).contentEquals(pending.before)) { "列表已改变，请重新预览" }
            val folder = File(filesDir, "backups").apply { mkdirs() }
            val backup = File.createTempFile("before-", ".lpl", folder)
            backup.outputStream().use {
                it.write(pending.before)
                it.fd.sync()
            }
            check(backup.readBytes().contentEquals(pending.before)) { "备份校验失败，未写入列表" }

            try {
                val stream = contentResolver.openOutputStream(pending.document, "rwt") ?: error("目录提供者拒绝写入")
                stream.use { it.write(pending.after) }
                check(read(pending.document).contentEquals(pending.after)) { "写入后的字节与预览不一致" }
            } catch (error: Exception) {
                throw IllegalStateException("写入未通过校验。原始内容备份于 ${backup.name}。\n${error.message}", error)
            }
            runOnUiThread {
                message = "测试列表已写入并读回校验。\n应用内备份 · ${backup.name}"
            }
        }
    }

    private fun read(uri: Uri): ByteArray =
        contentResolver.openInputStream(uri)?.use { it.readBytes() } ?: error("无法读取测试列表")

    private fun runOperation(status: String, work: () -> Unit) {
        running = true
        message = status
        refresh()
        worker.execute {
            try {
                work()
            } catch (error: Exception) {
                runOnUiThread { message = error.message ?: error.toString() }
            } finally {
                runOnUiThread {
                    running = false
                    if (!isDestroyed) refresh()
                }
            }
        }
    }

    private fun refresh() {
        choose.isEnabled = !running
        inspect.isEnabled = !running && grantedTree() != null
        apply.isEnabled = !running && preview != null
        if (pageReady) {
            page.evaluateJavascript("document.getElementById('status').textContent = ${JSONObject.quote(message)}", null)
        }
    }

    override fun onDestroy() {
        worker.shutdown()
        page.destroy()
        super.onDestroy()
    }

    private companion object {
        const val FIXTURE = "RAA-Probe.lpl"
        const val PICK_TREE = 100
        const val GRANT_FLAGS = Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION
    }
}
