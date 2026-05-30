from PIL import Image, ImageDraw
import os

# 创建 256x256 的扁平化风格头像
size = 256
img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

center = size // 2

# 扁平化背景 - 使用纯色
bg_color = (86, 182, 194)  # 蓝绿色
draw.ellipse([0, 0, size, size], fill=bg_color)

# 绘制更像真实头像的比例
# 头部 - 较小的圆形，位置偏上
head_radius = 35
head_y = 95
draw.ellipse([center - head_radius, head_y - head_radius,
              center + head_radius, head_y + head_radius],
             fill=(255, 255, 255, 255))

# 身体/肩膀 - 使用椭圆形状，更自然的肩膀轮廓
body_top = head_y + head_radius - 8
body_width = 100
body_height = 60
# 绘制肩膀椭圆
draw.ellipse([center - body_width//2, body_top,
              center + body_width//2, body_top + body_height],
             fill=(255, 255, 255, 255))

# 保存
img.save('app/static/avatars/default.png', 'PNG')
print('Better flat avatar created!')
