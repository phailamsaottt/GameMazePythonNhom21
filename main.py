import pygame  
import sys 
import config 
pygame.init() 
screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
pygame.display.set_caption(config.GAME_TITLE)
clock = pygame.time.Clock() 
while True :   #VONG LAP GAME
    
    for event in pygame.event.get() :
        if event.type == pygame.QUIT :
            pygame.quit()
            exit() 
        pygame.display.update() 
        clock.tick(60)
             
            