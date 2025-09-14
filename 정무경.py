import pygame
import os
import sys

# pygame 초기화
pygame.init()

# 바탕화면 경로 자동 가져오기
desktop = os.path.join(os.path.expanduser("~"), "Desktop")
image_path = os.path.join(desktop, "pygame test.jpg")

# 이미지 불러오기
image = pygame.image.load(image_path)

# 이미지 크기 확인
img_rect = image.get_rect()

# 스크린 생성 (이미지 크기에 맞게)
screen = pygame.display.set_mode((500, 600))
pygame.display.set_caption("Pygame Image Test")

# 메인 루프

while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    # 화면에 이미지 그리기
    screen.blit(image, (50, 50))
    pygame.display.flip()

# 종료
pygame.quit()