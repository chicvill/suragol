from PIL import Image
import os

source_path = r'C:\Users\USER\.gemini\antigravity\brain\e94e6c61-6d8e-41af-a269-7a17978aa526\mqnet_logo_512_1776000260014.png'
target_dir = r'c:\Users\USER\Dev\FreeOrder\static\images'

if not os.path.exists(target_dir):
    os.makedirs(target_dir)

img = Image.open(source_path)

# Save 512
img.save(os.path.join(target_dir, 'mqnet_icon_512.png'))

# Resize and save 192
img_192 = img.resize((192, 192), Image.LANCZOS)
img_192.save(os.path.join(target_dir, 'mqnet_icon_192.png'))

print("Icons saved successfully.")
