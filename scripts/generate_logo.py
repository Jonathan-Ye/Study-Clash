from PIL import Image, ImageDraw, ImageFont
import os

# 创建 512x512 的Logo
size = 512
img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

center = size // 2

# 背景圆形 - 使用蓝绿色主题
bg_color = (86, 182, 194)
draw.ellipse([20, 20, size-20, size-20], fill=bg_color)

# 绘制书本/学习图标
# 书本主体
book_left = 140
book_right = 372
book_top = 140
book_bottom = 380

# 书本封面
draw.rounded_rectangle([book_left, book_top, book_right, book_bottom], 
                       radius=15, fill=(255, 255, 255, 255))

# 书脊（左侧阴影效果）
draw.rounded_rectangle([book_left, book_top, book_left + 30, book_bottom], 
                       radius=15, fill=(240, 240, 240, 255))

# 书本内页线条（模拟页面）
for i in range(5):
    y = book_top + 60 + i * 45
    draw.rectangle([book_left + 50, y, book_right - 30, y + 8], 
                   fill=(230, 230, 230, 255))

# 添加"学"字或字母"S"
try:
    # 尝试使用系统字体
    font = ImageFont.truetype("arial.ttf", 120)
except:
    font = ImageFont.load_default()

# 在书本中央添加字母
text = "S"
bbox = draw.textbbox((0, 0), text, font=font)
text_width = bbox[2] - bbox[0]
text_height = bbox[3] - bbox[1]
text_x = center - text_width // 2
text_y = center - text_height // 2 - 10

draw.text((text_x, text_y), text, font=font, fill=bg_color)

# 保存不同尺寸的Logo
img.save('app/static/images/logo.png', 'PNG')

# 创建小尺寸版本
small = img.resize((128, 128), Image.Resampling.LANCZOS)
small.save('app/static/images/logo-small.png', 'PNG')

# 创建白色文字版本的Logo（用于深色背景）
img_white = Image.new('RGBA', (size, size), (0, 0, 0, 0))
draw_white = ImageDraw.Draw(img_white)
draw_white.ellipse([20, 20, size-20, size-20], fill=(255, 255, 255, 255))
draw_white.rounded_rectangle([book_left, book_top, book_right, book_bottom], 
                              radius=15, fill=bg_color)
draw_white.rounded_rectangle([book_left, book_top, book_left + 30, book_bottom], 
                              radius=15, fill=(70, 160, 170, 255))
for i in range(5):
    y = book_top + 60 + i * 45
    draw_white.rectangle([book_left + 50, y, book_right - 30, y + 8], 
                         fill=(100, 190, 200, 255))
draw_white.text((text_x, text_y), text, font=font, fill=(255, 255, 255, 255))
img_white.save('app/static/images/logo-white.png', 'PNG')

print('Logo generated successfully!')
print('- logo.png (512x512)')
print('- logo-small.png (128x128)')
print('- logo-white.png (512x512, for dark background)')
