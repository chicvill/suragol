import os
import shutil
from PIL import Image

def generate_icons():
    # 원본 이미지 경로 (스크립트 실행 위치 기준)
    source_img = os.path.join(os.getcwd(), "assets", "icon-only.png")
    
    if not os.path.exists(source_img):
        # 만약 assets 폴더에 없다면 아까 그 긴 임시 경로에서 직접 가져오기 시도
        alt_source = r"C:\Users\USER\.gemini\antigravity\brain\87bf44b1-1623-404e-93c4-aabf28dd8cfb\mqnet_app_icon_v1_1775717610547.png"
        if os.path.exists(alt_source):
            source_img = alt_source
        else:
            print(f"❌ 원본 이미지를 찾을 수 없습니다: {source_img}")
            return

    # 안드로이드 리소스 경로
    res_base = os.path.join(os.getcwd(), "android", "app", "src", "main", "res")
    
    if not os.path.exists(res_base):
        print(f"❌ 안드로이드 리소스 폴더를 찾을 수 없습니다: {res_base}")
        print("힌트: 'npx cap add android'가 성공적으로 완료되었는지 확인해 주세요.")
        return

    icon_configs = [
        ("mipmap-mdpi", 48),
        ("mipmap-hdpi", 72),
        ("mipmap-xhdpi", 96),
        ("mipmap-xxhdpi", 144),
        ("mipmap-xxxhdpi", 192)
    ]

    try:
        img = Image.open(source_img).convert("RGBA")
        for folder, size in icon_configs:
            folder_path = os.path.join(res_base, folder)
            if not os.path.exists(folder_path):
                os.makedirs(folder_path, exist_ok=True)
                
            # 파일 저장 (ic_launcher.png, ic_launcher_round.png)
            resized = img.resize((size, size), Image.Resampling.LANCZOS)
            resized.save(os.path.join(folder_path, "ic_launcher.png"))
            resized.save(os.path.join(folder_path, "ic_launcher_round.png"))
            print(f"✅ {folder} 적용 완료 ({size}x{size})")

        print("\n✨ [성공] MQnet 아이콘이 안드로이드 프로젝트에 완벽하게 박혔습니다!")
        print("이제 Android Studio에서 재생(▶) 버튼을 누르시면 됩니다.")
    except Exception as e:
        print(f"❌ 작업 중 에러 발생: {e}")

if __name__ == "__main__":
    generate_icons()
