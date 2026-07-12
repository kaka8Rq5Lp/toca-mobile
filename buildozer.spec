[app]

title = Toca Mobile
package.name = tocamobile
package.domain = com.tocastudio

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json

version = 1.0

requirements = python3,kivy,kivymd,pyjnius,android

orientation = portrait

fullscreen = 0

android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,MANAGE_EXTERNAL_STORAGE,ACCESS_NETWORK_STATE

android.api = 33
android.minapi = 24
android.ndk = 25b
android.sdk = 33
android.accept_sdk_license = True

android.arch = arm64-v8a
android.arch_filters = arm64-v8a,armeabi-v7a

android.release_artifact = apk

android.allow_backup = True
android.private_storage = True

log_level = 2

android.enable_androidx = True

# Icon
icon.filename = %(source.dir)s/icon.png

# Presplash (optional)
# presplash.filename = %(source.dir)s/presplash.png

# Entry point
source.entry_point = main.py
