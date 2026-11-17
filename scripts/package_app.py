#!/usr/bin/env python3
"""Build and package Oink.app and DMG for macOS 12 (x86_64)."""
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-support'))
sys.path.insert(0, str(ROOT / 'packaging/macos'))

from localizations import DECLARATIONS, STRINGS, write_localizations
from payload import copy_notices

I = json.loads((ROOT / 'packaging/identity.json').read_text())
VERSION = I['version']
BUILD = 306001  # encode_build("0.3.6", 1)
ARCH = 'x86_64'
MIN_OS = I['macos_minimum']
TEAM_ID = I['macos']['team_id']
APP_GROUP = TEAM_ID + '.' + I['macos']['app_group_suffix']
BIN = I['binaries']

DIST_DIR = ROOT / 'dist'
DIST_DIR.mkdir(parents=True, exist_ok=True)
STAGING_DIR = ROOT / 'target/macos-staging'
if STAGING_DIR.exists():
    shutil.rmtree(STAGING_DIR)
STAGING_DIR.mkdir(parents=True)

APP_DIR = STAGING_DIR / I['macos']['app']
MAC_DIR = APP_DIR / 'Contents/MacOS'
RES_DIR = APP_DIR / 'Contents/Resources'
MAC_DIR.mkdir(parents=True)
RES_DIR.mkdir(parents=True)

print("1. Copying Rust release binaries...")
for role in ['backend', 'agent', 'crash_collector']:
    src = ROOT / 'target/release' / BIN[role]
    dest = MAC_DIR / BIN[role]
    shutil.copy2(src, dest)
    os.chmod(dest, 0o755)

print("2. Copying resources and icons...")
shutil.copy2(ROOT / 'apps/oink/src-tauri/icons/icon.icns', RES_DIR / 'icon.icns')
copy_notices(RES_DIR)

# Embedded update notes
notes_file = RES_DIR / 'embedded-update-notes.json'
notes_file.write_text(json.dumps({
    "build": BUILD,
    "version": VERSION,
    "notes": "macOS 12.3+ compatible build for x86_64"
}, indent=2) + "\n")

# Build metadata
build_meta = {
    "schema": 1,
    "product": I['name'],
    "version": VERSION,
    "build": BUILD,
    "minimum_os": MIN_OS,
    "architecture": "x64",
    "signing": "ad-hoc"
}
(RES_DIR / I['metadata_file']).write_text(json.dumps(build_meta, indent=2) + "\n")

print("3. Building UI Helper bundle (Contents/Helpers/Oink.app)...")
HELPER_DIR = APP_DIR / 'Contents/Helpers/Oink.app'
HELPER_MAC = HELPER_DIR / 'Contents/MacOS'
HELPER_RES = HELPER_DIR / 'Contents/Resources'
HELPER_MAC.mkdir(parents=True)
HELPER_RES.mkdir(parents=True)

shutil.copy2(ROOT / 'target/release' / BIN['ui'], HELPER_MAC / BIN['ui'])
os.chmod(HELPER_MAC / BIN['ui'], 0o755)
shutil.copy2(RES_DIR / 'icon.icns', HELPER_RES / 'icon.icns')

helper_info = dict(
    CFBundleExecutable=BIN['ui'],
    CFBundleIdentifier=I['macos']['ui_id'],
    CFBundleName=I['name'],
    CFBundleDisplayName=I['name'],
    CFBundlePackageType='APPL',
    CFBundleShortVersionString=VERSION,
    CFBundleVersion=str(BUILD),
    CFBundleGetInfoString=VERSION,
    CFBundleIconFile='icon.icns',
    LSMinimumSystemVersion=MIN_OS,
    LSUIElement=True,
    NSHighResolutionCapable=True,
    **DECLARATIONS
)
(HELPER_DIR / 'Contents/Info.plist').write_bytes(plistlib.dumps(helper_info))
write_localizations(HELPER_DIR)

print("4. Building Audio Plugin Driver...")
PLUGIN_DIR = RES_DIR / 'AudioPlugin'
PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
if (Path('/tmp/audio-plugin-build/OinkMicrophone.driver')).exists():
    shutil.copytree('/tmp/audio-plugin-build/OinkMicrophone.driver', PLUGIN_DIR / 'OinkMicrophone.driver')
    shutil.copy2(ROOT / 'apps/audio-plugin/install.sh', PLUGIN_DIR / 'install.sh')
    os.chmod(PLUGIN_DIR / 'install.sh', 0o755)

print("5. Building Swift components...")
TMP_SWIFT = ROOT / 'target/swift-build'
TMP_SWIFT.mkdir(parents=True, exist_ok=True)

# ReleaseIdentity.swift
gen_identity = TMP_SWIFT / 'ReleaseIdentity.swift'
gen_identity.write_text('enum ReleaseIdentity {\n' + '\n'.join(
    f'    static let {k} = {json.dumps(v)}' for k, v in {
        'appGroupKey': I['macos']['app_group_key'],
        'domain': I['macos']['file_provider_domain'],
        'displayName': I['name'],
        'subsystem': I['macos']['file_provider_id']
    }.items()
) + '\n}\n')

# Manager plist
manager_plist = TMP_SWIFT / 'manager.plist'
manager_plist.write_bytes(plistlib.dumps({
    'CFBundleIdentifier': I['bundle_id'],
    'CFBundleName': I['name'],
    'CFBundleShortVersionString': VERSION,
    'CFBundleVersion': str(BUILD),
    I['macos']['app_group_key']: APP_GROUP
}))

# Clang crash capture
subprocess.run(['xcrun', 'clang', '-O2', '-g', '-std=c11', f'-target', f'{ARCH}-apple-macos{MIN_OS}',
    '-c', str(ROOT / 'apps/file-provider/CrashCapture.c'), '-o', str(TMP_SWIFT / 'crash-capture.o')], check=True)

swift_common = [
    'xcrun', 'swiftc', '-swift-version', '5', '-O', '-g',
    '-module-cache-path', '/tmp/swift-cache',
    '-target', f'{ARCH}-apple-macos{MIN_OS}',
    '-parse-as-library', '-D', 'OINK_RELEASE'
]

# Finder extension
FINDER_DIR = APP_DIR / 'Contents/PlugIns/OinkFinderSync.appex'
FINDER_MAC = FINDER_DIR / 'Contents/MacOS'
FINDER_RES = FINDER_DIR / 'Contents/Resources'
FINDER_MAC.mkdir(parents=True)
FINDER_RES.mkdir(parents=True)

for name in ('OinkPasteMenu.png', 'OinkPasteMenu@2x.png',
             'OinkPasteMenuDark.png', 'OinkPasteMenuDark@2x.png'):
    shutil.copy2(ROOT / 'apps/finder-sync/Resources' / name, FINDER_RES / name)

finder_info = dict(
    CFBundleIdentifier=I['bundle_id'] + '.findersync',
    CFBundleName='Oink Finder',
    CFBundleExecutable='OinkFinderSync',
    CFBundlePackageType='XPC!',
    CFBundleShortVersionString=VERSION,
    CFBundleVersion=str(BUILD),
    CFBundleGetInfoString=VERSION,
    LSMinimumSystemVersion=MIN_OS,
    OinkAppGroup=APP_GROUP,
    NSExtension=dict(
        NSExtensionPointIdentifier='com.apple.FinderSync',
        NSExtensionPrincipalClass='OinkFinderSync'
    ),
    **DECLARATIONS
)
(FINDER_DIR / 'Contents/Info.plist').write_bytes(plistlib.dumps(finder_info))
write_localizations(FINDER_DIR)

subprocess.run(swift_common + [
    '-module-name', 'OinkFinderSync', '-application-extension',
    '-Xlinker', '-e', '-Xlinker', '_OinkFinderSyncMain', '-l', 'extension',
    str(ROOT / 'apps/finder-sync/Request.swift'),
    str(ROOT / 'apps/finder-sync/ExtensionMain.swift'),
    str(ROOT / 'apps/finder-sync/Extension.swift'),
    '-o', str(FINDER_MAC / 'OinkFinderSync')
], check=True)

# Paste Helper (Contents/Helpers/OinkPaste.app)
PASTE_DIR = APP_DIR / 'Contents/Helpers/OinkPaste.app'
PASTE_MAC = PASTE_DIR / 'Contents/MacOS'
PASTE_MAC.mkdir(parents=True)

paste_info = dict(
    CFBundleIdentifier=I['bundle_id'] + '.paste',
    CFBundleName='Oink Paste',
    CFBundleExecutable='OinkPaste',
    CFBundlePackageType='APPL',
    CFBundleShortVersionString=VERSION,
    CFBundleVersion=str(BUILD),
    CFBundleGetInfoString=VERSION,
    LSMinimumSystemVersion=MIN_OS,
    LSUIElement=True,
    OinkAppGroup=APP_GROUP,
    **DECLARATIONS
)
(PASTE_DIR / 'Contents/Info.plist').write_bytes(plistlib.dumps(paste_info))
write_localizations(PASTE_DIR)

subprocess.run(swift_common + [
    str(ROOT / 'apps/finder-sync/Request.swift'),
    str(ROOT / 'apps/finder-sync/Helper.swift'),
    '-o', str(PASTE_MAC / 'OinkPaste')
], check=True)

# File provider extension (Contents/PlugIns/OinkFileProvider.appex)
FP_EXT_DIR = APP_DIR / 'Contents/PlugIns' / I['macos']['file_provider_bundle']
FP_EXT_MAC = FP_EXT_DIR / 'Contents/MacOS'
FP_EXT_MAC.mkdir(parents=True)

fp_info = dict(
    CFBundleIdentifier=I['macos']['file_provider_id'],
    CFBundleName=I['macos']['file_provider_name'],
    CFBundleExecutable=BIN['file_provider_extension'],
    CFBundlePackageType='XPC!',
    CFBundleShortVersionString=VERSION,
    CFBundleVersion=str(BUILD),
    CFBundleGetInfoString=VERSION,
    LSMinimumSystemVersion=MIN_OS,
    **DECLARATIONS
)
fp_info[I['macos']['app_group_key']] = APP_GROUP
fp_info['NSExtension'] = dict(
    NSExtensionPointIdentifier='com.apple.fileprovider-nonui',
    NSExtensionPrincipalClass=BIN['file_provider_class'],
    NSExtensionFileProviderDocumentGroup=APP_GROUP,
    NSExtensionFileProviderSupportsEnumeration=True,
    NSFileProviderUserInteractions=[]
)
(FP_EXT_DIR / 'Contents/Info.plist').write_bytes(plistlib.dumps(fp_info))
write_localizations(FP_EXT_DIR)

subprocess.run(swift_common + [
    '-module-name', BIN['file_provider_extension'],
    '-application-extension', '-Xlinker', '-e', '-Xlinker', '_OinkFileProviderMain', '-l', 'extension',
    str(ROOT / 'apps/file-provider/ExtensionMain.swift'),
    str(ROOT / 'apps/file-provider/Upgrade.swift'),
    str(ROOT / 'apps/file-provider/ContainerCleanup.swift'),
    str(gen_identity),
    str(ROOT / 'apps/file-provider/Shared.swift'),
    str(ROOT / 'apps/file-provider/ReportCapture.swift'),
    str(ROOT / 'apps/file-provider/Extension.swift'),
    str(TMP_SWIFT / 'crash-capture.o'),
    '-o', str(FP_EXT_MAC / BIN['file_provider_extension'])
], check=True)

# File provider manager (Contents/MacOS/oink-file-provider)
subprocess.run(swift_common + [
    '-Xlinker', '-sectcreate', '-Xlinker', '__TEXT', '-Xlinker', '__info_plist',
    '-Xlinker', str(manager_plist),
    str(gen_identity),
    str(ROOT / 'apps/file-provider/Shared.swift'),
    str(ROOT / 'apps/file-provider/Upgrade.swift'),
    str(ROOT / 'apps/file-provider/ContainerCleanup.swift'),
    str(ROOT / 'apps/file-provider/Uninstall.swift'),
    str(ROOT / 'apps/file-provider/NativeReceived.swift'),
    str(ROOT / 'apps/file-provider/Manager.swift'),
    '-o', str(MAC_DIR / BIN['file_provider_manager'])
], check=True)

print("6. Writing main App Info.plist and localizations...")
main_info = dict(
    CFBundleExecutable=BIN['backend'],
    CFBundleIdentifier=I['bundle_id'],
    CFBundleName=I['name'],
    CFBundleDisplayName=I['name'],
    CFBundlePackageType='APPL',
    CFBundleShortVersionString=VERSION,
    CFBundleVersion=str(BUILD),
    CFBundleGetInfoString=VERSION,
    CFBundleIconFile='icon.icns',
    LSMinimumSystemVersion=MIN_OS,
    LSUIElement=True,
    NSHighResolutionCapable=True,
    NSBonjourServices=[I['bonjour_service']],
    **DECLARATIONS
)
main_info.update(STRINGS['en'])
main_info[I['macos']['app_group_key']] = APP_GROUP
(APP_DIR / 'Contents/Info.plist').write_bytes(plistlib.dumps(main_info))
write_localizations(APP_DIR, permissions=True)

print("7. Codesigning components...")
host_ent = TMP_SWIFT / 'host.plist'
host_ent.write_bytes(plistlib.dumps({
    'com.apple.security.application-groups': [APP_GROUP],
    'com.apple.security.device.audio-input': True
}))
paste_ent = TMP_SWIFT / 'paste-host.plist'
paste_ent.write_bytes(plistlib.dumps({
    'com.apple.security.application-groups': [APP_GROUP]
}))
finder_ent = TMP_SWIFT / 'finder.plist'
finder_ent.write_bytes(plistlib.dumps({
    'com.apple.security.application-groups': [APP_GROUP],
    'com.apple.security.app-sandbox': True
}))
ext_ent = TMP_SWIFT / 'extension.plist'
ext_ent.write_bytes(plistlib.dumps({
    'com.apple.security.application-groups': [APP_GROUP],
    'com.apple.security.app-sandbox': True,
    'com.apple.security.network.client': True
}))

def sign(target, ident, ent=None):
    cmd = ['codesign', '--force', '--options', 'runtime', '-s', '-', '--identifier', ident]
    if ent:
        cmd += ['--entitlements', str(ent)]
    cmd.append(str(target))
    subprocess.run(cmd, check=True)

if (PLUGIN_DIR / 'OinkMicrophone.driver').exists():
    sign(PLUGIN_DIR / 'OinkMicrophone.driver', 'com.hachiwii.oink.microphone.driver')
sign(FINDER_DIR, I['bundle_id'] + '.findersync', finder_ent)
sign(PASTE_DIR, I['bundle_id'] + '.paste', paste_ent)
sign(FP_EXT_DIR, I['macos']['file_provider_id'], ext_ent)
sign(MAC_DIR / BIN['file_provider_manager'], I['bundle_id'] + '.file-provider-manager', host_ent)
sign(HELPER_DIR, I['macos']['ui_id'])
sign(MAC_DIR / BIN['agent'], I['macos']['agent_id'])
sign(MAC_DIR / BIN['crash_collector'], I['bundle_id'] + '.crash-collector')
sign(APP_DIR, I['bundle_id'], host_ent)

print("8. Creating DMG installer...")
DMG_STAGING = ROOT / 'target/dmg-staging'
if DMG_STAGING.exists():
    shutil.rmtree(DMG_STAGING)
DMG_STAGING.mkdir(parents=True)

# Copy Oink.app to DMG staging
shutil.copytree(APP_DIR, DMG_STAGING / 'Oink.app', symlinks=True)
# Symlink /Applications
os.symlink('/Applications', DMG_STAGING / 'Applications')

DMG_PATH = DIST_DIR / f'Oink-{VERSION}-macos-x64.dmg'
if DMG_PATH.exists():
    DMG_PATH.unlink()

subprocess.run([
    'hdiutil', 'create',
    '-volname', 'Oink',
    '-srcfolder', str(DMG_STAGING),
    '-ov',
    '-format', 'UDZO',
    str(DMG_PATH)
], check=True)

# Sign DMG
subprocess.run(['codesign', '--force', '-s', '-', str(DMG_PATH)], check=True)

print(f"\n==========================================")
print(f"Build complete!")
print(f"Application Bundle: {APP_DIR}")
print(f"DMG Installer:      {DMG_PATH}")
print(f"==========================================")
