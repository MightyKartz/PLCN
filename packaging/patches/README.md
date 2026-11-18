# macOS MTP session recovery

`scripts/prepare_mtp.py` builds the checksum-pinned libmtp 1.1.23 source archive with `libmtp-1.1.23-unlock-recovery.patch`. The desktop packager includes this build and its LGPL license instead of an unpatched Homebrew dylib.

The failure cleanup follows [libmtp's upstream `close_usb_after_failure` implementation](https://github.com/libmtp/libmtp/blob/master/src/libusb1-glue.c): release the interface and close its handle without further status requests or USB resets. The application build also:

- Releases handles when interface initialization fails.
- Returns after the initial five-second session-open timeout rather than resetting a locked device and retrying for a minute.
- Provides `LIBMTP_Probe_Storage`, which temporarily uses a three-second timeout for discovery and restores the normal transfer timeout afterward.
- Limits session-close control requests to one second.
- Skips reset-on-close on macOS for the connected Qualcomm handheld's Google MTP identity (`18d1:4ee1`). A USB reset left this firmware unresponsive until cable reconnection during live diagnosis.

Normal file-transfer timeouts and read-back verification remain in place. Discovery never writes game files.

Build on macOS with Xcode command-line tools, pkg-config and libusb available:

```sh
python3 scripts/prepare_mtp.py
python3 scripts/package_desktop.py --arch arm64
```

Regression coverage includes cached-session release after a locked storage probe, reopening on unlock, and stopping automatic retries after a ready result. Physical lock/unlock recovery must also be checked in the installed native app.
