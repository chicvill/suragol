import os, glob, shutil

print("=== 수라골 참숯갈비 이미지 복사 스크립트 ===")
base_dir = r"C:\Users\USER\.gemini\antigravity\brain\a12b6296-2531-461a-80a0-70328ad88362"
static_dir = os.path.join(os.path.dirname(__file__), "static", "images")
os.makedirs(static_dir, exist_ok=True)

types = ['pork', 'beef', 'noodle', 'stew', 'meal', 'egg']
copied = 0

for t in types:
    files = glob.glob(os.path.join(base_dir, f"{t}_*.png"))
    if files:
        latest_file = max(files, key=os.path.getctime)
        dest = os.path.join(static_dir, f"{t}.png")
        shutil.copy(latest_file, dest)
        print(f"적용 완료: {t}.png")
        copied += 1

print(f"총 {copied}개의 고퀄리티 음식이미지가 /static/images에 적용되었습니다.")
print("웹 탭을 새로고침 하시면 메뉴판에 반영됩니다!")
