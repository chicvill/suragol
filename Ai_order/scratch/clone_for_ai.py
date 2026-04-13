import os
import shutil

def clone_project():
    source = "."
    target = "Ai_order"
    
    # 제외할 폴더 및 파일
    exclude = {'.venv', '.git', '__pycache__', '.gemini', 'Ai_order', 'exclude_list.txt'}
    
    if not os.path.exists(target):
        os.makedirs(target)
        print(f"Created directory: {target}")
    
    for item in os.listdir(source):
        s = os.path.join(source, item)
        t = os.path.join(target, item)
        
        if item in exclude:
            continue
            
        if os.path.isdir(s):
            if os.path.exists(t):
                shutil.rmtree(t)
            shutil.copytree(s, t)
            print(f"Copied directory: {item}")
        else:
            shutil.copy2(s, t)
            print(f"Copied file: {item}")

if __name__ == "__main__":
    clone_project()
    print("\n✅ AI_order folder clone completed successfully.")
