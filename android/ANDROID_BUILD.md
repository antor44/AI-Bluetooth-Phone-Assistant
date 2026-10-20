# Building the AI Switchboard Android app (APK)

These steps produce a signed **release APK** that people can install directly (outside Google Play).

## 0. What you need
* **Android Studio** (current stable). It bundles the JDK and the Gradle tooling.
* **Android SDK Platform 36** (the project uses `compileSdk = 36` / `targetSdk = 36`). Install it from *Tools → SDK Manager*.
* The project folder (the one with `settings.gradle.kts`, a root `build.gradle.kts` and the `app/` module).

## 1. Put the sources in place
1. Replace `app/build.gradle.kts` with the provided one (adds WorkManager, Android 16 target, version `1.0.0`).
2. Copy the contents of the provided `src/` over `app/src/` (accept replacing). This adds the notification code, the *About* screen, the icons and the license texts in `app/src/main/assets/licenses/`.
3. Check that `app/src/main/assets/licenses/` contains `GPL-3.0.txt`, `Apache-2.0.txt` and `BSD-3-Clause.txt` — the *About → Licenses* screen reads them.
4. Open the project in Android Studio and press **Sync Project with Gradle Files** (elephant icon). If it complains that the Android Gradle Plugin does not support `compileSdk 36`, accept the suggested upgrade of the plugin (*AGP Upgrade Assistant*).

## 2. Check it before releasing
1. **Build → Clean Project**, then **Build → Rebuild Project**. Fix any compile error shown in the *Build* panel before continuing.
2. Run it on a device or emulator (*Run ▶*). Test: pairing, the panel loading, the **Notifications** switch, and **About** (version, licenses).
3. Test on an **old phone (Android 7–9)** and a **recent one** if you can. Notification permission is only requested on Android 13+.
4. In the Google Play Console you will also be asked about 16 KB memory pages (Tor ships native libraries); for an APK outside Google Play it does not block you.

## 3. Create your signing key (once)
A release APK must be signed. **The same key must sign every future update**; if you lose it, users have to uninstall and reinstall.
1. **Build → Generate Signed App Bundle / APK…** → choose **APK** → *Next*.
2. *Key store path* → **Create new…** Save the `.jks` file **outside the project folder** (never commit it to GitHub).
3. Fill in a password for the keystore and for the key, an alias (e.g. `aiswitchboard`), a validity of 25+ years, and your name.
4. **Make a backup of the `.jks` file and the passwords** (password manager + an offline copy).

## 4. Generate the APK
1. In the same wizard select your keystore, alias and passwords → *Next*.
2. Choose the **release** build variant and tick both signature versions (**V1 and V2**) → *Create*.
3. The APK appears in `app/release/app-release.apk` (Android Studio shows a *locate* link).
4. Rename it to `AI-Switchboard.apk` (or include the version, e.g. `AI-Switchboard-1.0.0.apk`).

## 5. Verify it
```bash
# Signature (apksigner is in <Android SDK>/build-tools/<version>/)
apksigner verify --print-certs AI-Switchboard.apk
# Install on a connected phone with USB debugging
adb install -r AI-Switchboard.apk
# Checksum to publish with the release
sha256sum AI-Switchboard.apk
```

## 6. Publish
* Put the APK in the repository at `android/AI-Switchboard.apk` (the README download link points there) **and** attach it to the GitHub release, pasting the SHA-256 in the release text.
* GitHub rejects files over 100 MB (warns above 50 MB). If the APK is too big because of Tor's native libraries, keep only the processors you need by adding to `defaultConfig` in `app/build.gradle.kts`:
  ```kotlin
  ndk { abiFilters += listOf("arm64-v8a", "armeabi-v7a") }
  ```
  (this removes x86 support, so emulators on PC will no longer run that build).
* **Next versions:** raise `versionCode` by 1 (and `versionName`) in `app/build.gradle.kts` before each release and sign with the same key.

## 7. License checklist (GPL v3)
* The repository contains the full source code and the `LICENSE` file (GPL v3). ✔
* The app shows the license notice, a link to the source code and the full GPL text (*About*). ✔
* Third-party licenses are bundled and shown: Tor (BSD 3-Clause), AndroidX/Kotlin/Coroutines (Apache 2.0), Noto Emoji artwork (Apache 2.0). ✔
* If you replace the icon with your own artwork, update the *Noto Emoji* line in `AboutDialog.kt` (and in the README).
* The Google Play services code scanner is a proprietary component used only for the optional QR scan: it is not distributed with your code. Projects that must contain only free software (for example F-Droid) cannot include it; replacing it by an open-source scanner would be needed there.
* Tor's own build also contains other libraries (for example OpenSSL, libevent, zlib). If you want a fully complete third-party notice, add their license texts from `https://github.com/guardianproject/tor-android` to the *Licenses* list.

## Common problems
| Problem | Solution |
|---|---|
| *Unsupported compileSdk 36* | Update the Android Gradle Plugin (Android Studio's upgrade assistant) |
| *Unresolved reference: R.drawable.ic_stat_notify* | The `res/drawable-*dpi/ic_stat_notify.png` files are missing: copy the `res/` folder again |
| Build error in `PollWorker`/`Notifications` | `androidx.work:work-runtime-ktx` missing: use the provided `app/build.gradle.kts` and sync |
| *The keystore was tampered with, or password incorrect* | Wrong keystore/key password |
| The APK installs but the old icon stays | Uninstall the previous version first; the launcher caches icons |
