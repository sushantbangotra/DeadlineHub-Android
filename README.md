# DeadlineHub for Android

An offline-first Android adaptation of your Flask website, with a separate Python sync server.

**This download is a source-code project, not an APK.** The web bundle and sync API were tested. The native Android build and phone notifications still require Android Studio or the included GitHub build workflow and testing on a phone.

## What you can use

- Add, edit, complete and delete deadlines without internet.
- Categories, priorities, due-date sorting, search, filters and completion counts.
- Monthly calendar and date-specific deadline lists.
- Plain-text notes, search and pinning.
- Dark and light appearance based on the original website's palette.
- Optional Android reminders at 9 AM on each due date.
- Register/sign in to sync across devices through the included server.
- Offline account workspaces, queued changes and automatic sync while open or when resumed.
- Conflicting edits are kept as separate copies. A stale deletion cannot erase newer server work.

## Start here: make an installable APK

### Option A — Android Studio on your computer

Install Node.js 22 or newer and Android Studio 2025.2.1 or newer. In Android Studio's SDK Manager install Android SDK Platform 36. Use Android Studio's bundled JDK 21 or newer.

1. Extract this ZIP.
2. Open a terminal in `DeadlineHub-Android` (the folder containing `package.json`).
3. Run:

```sh
npm ci
npm run android
npx cap open android
```

4. Wait for Android Studio's Gradle sync to finish.
5. Connect your Android phone with USB debugging enabled, or start an emulator.
6. Press Run to install and launch DeadlineHub.
7. To create a shareable debug APK, use Android Studio's Build APK action, or run:

```sh
cd android
# macOS / Linux
./gradlew assembleDebug
# Windows
# gradlew.bat assembleDebug
```

Your APK appears at `android/app/build/outputs/apk/debug/app-debug.apk`.

The Android project already exists. Do not run `cap add android` again. After changing app code, run `npm run android` before building.

### Option B — GitHub builds the APK

1. Create a private GitHub repository.
2. Upload the **contents** of `DeadlineHub-Android`, including `.github/workflows/android.yml`. `package.json` must be at the repository root.
3. Open its Actions tab and select **Build Android APK**.
4. Choose **Run workflow**.
5. When it succeeds, download **DeadlineHub-debug-apk** from Artifacts.
6. Extract it and install the APK on your phone. Android may ask you to allow installation from that source.

This workflow is included but has not been run on your GitHub account. It builds a debug APK for testing. For Play Store distribution, use a release keystore and signed Android App Bundle; keep that keystore private and backed up. A debug APK from a later workflow may have a different signing key. Avoid uninstalling an existing build with unsynced data; use a stable signing key for ongoing use.

## Use it offline immediately

The app opens in a local workspace. No account or server is needed to add deadlines and notes. Android bundles the full interface inside the app.

The browser development preview is not a separately installed offline PWA. Use the Android build for offline cold starts.

## Enable online sync

Online sync needs the supplied Python server hosted at an HTTPS address. The app does not include a hosted service.

### Test the server on your computer

```sh
cd server
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows instead: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

It runs at `http://127.0.0.1:8000`. For a browser test, from the project root run `npm run dev`, open the displayed local URL, and use `http://127.0.0.1:8000` as the sync server. Plain HTTP is allowed only for localhost browser development. The Android application intentionally requires HTTPS.

### Host for your phone

Deploy the `server` directory to a Python/Docker host with:

- HTTPS in front of the application.
- A persistent disk mounted at `/data`.
- `DATABASE_PATH=/data/deadlinehub-mobile.db`.
- `ALLOWED_ORIGINS=https://localhost` for the Android app; add any approved browser origin as a comma-separated value if needed.
- Start command: `gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 4 --timeout 60 app:app`.

A Dockerfile is included. Do not use ephemeral server storage for the SQLite file. Back it up using SQLite's online backup API or with the server stopped. The database contains private user records. Do not put it in a public repository.

In the app, open **Account → Set up sync**, enter your HTTPS server URL, email and a password of at least 10 characters, and choose **Create account**. On a second phone, use the same URL and sign in with that account.

Local workspace items are separate. To copy them into your account, choose **Copy local items to this account** once. Repeating the copy duplicates items. Account sign-in needs internet; the account workspace then works offline. Sessions expire after 30 days; signing in again restores sync without discarding local edits.

Sync happens after edits, every minute while active, when connectivity returns and when the app resumes. It does not continuously sync with the app closed. Keep the server address stable: local workspaces are scoped to both server URL and account ID.

## Reminders and storage

Enable reminders in Account and grant the Android notification permission. The app schedules the next 100 future incomplete deadlines at 9 AM on the due date, in the phone's timezone. Dates whose 9 AM time has passed are not scheduled retroactively. Battery restrictions, denied permissions or Android's alarm settings can delay delivery. Open the app after timezone changes to refresh schedules. This is not a server push notification service.

Device data is kept in IndexedDB inside the Android app's private WebView. Session information uses Capacitor Preferences. Neither is a separate encrypted vault; protect the phone with its screen lock. Android app backup is disabled to avoid copying session information. Removing the app or clearing its data deletes unsynced work. Sync and confirm completion before changing phones.

## Differences from your original website

This is a first mobile version, not a byte-for-byte wrapper of Flask pages. It retains the primary deadlines/notes workflow and color palette, with a redesigned phone layout.

- Notes are plain text in this version; rich-text formatting is not included.
- Website PIN login, password recovery, profile/password editing and keyboard shortcuts are not included.
- Existing website accounts, notes and deadlines are **not automatically imported**. The original database is not packaged in this project.
- The sync server is separate from the old Flask website. Running the old website alone will not sync mobile data. A migration/integration step is needed if both must share the old database.
- Email verification, account deletion, password reset and a production operations setup remain future work before a public multi-user launch.

## Project layout

- `src/`: mobile screens, offline persistence, sync merge logic and reminder scheduling.
- `android/`: native Android Studio project, including Gradle wrapper.
- `server/`: Flask + SQLite account and sync API, Dockerfile and API tests.
- `tests/`: merge tests and browser integration test.
- `.github/workflows/android.yml`: debug APK build workflow.
- `dist/`: tested production web bundle.

## Validation

```sh
npm ci
npm test
npm run android
cd server
pip install -r requirements.txt
python -m unittest -v test_api.py
cd ..
npx playwright install chromium
npx playwright test
```

The browser test uses a temporary test database and covers offline editing, reload persistence, notes, themes, account creation, local-to-account copy, and another device retrieving synced records. Native APK installation, notification timing, reboot behavior and Android back-button behavior must still be tested on a phone.

Framework reference: https://capacitorjs.com/docs/getting-started/environment-setup
