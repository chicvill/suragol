import shutil
import os

# 1. 폴더 생성
if not os.path.exists('assets'):
    os.makedirs('assets')

# 2. 이미지 복사
source = r"C:\Users\USER\.gemini\antigravity\brain\87bf44b1-1623-404e-93c4-aabf28dd8cfb\mqnet_app_icon_v1_1775717610547.png"
targets = [
    'assets/logo.png',
    'assets/icon-only.png',
    'assets/icon-foreground.png',
    'assets/icon-background.png',
    'assets/splash.png',
    'assets/splash-dark.png'
]

for t in targets:
    shutil.copy(source, t)
    print(f"✅ Copied to {t}")
