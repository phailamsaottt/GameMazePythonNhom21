import sys
import pygame
import config

from menu import MenuScreen
from race import RaceScreen
from play import PlayingScreen


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
    pygame.display.set_caption(config.GAME_TITLE)
    clock = pygame.time.Clock()


    current_state = config.STATE_MENU

  
    menu_screen = MenuScreen(screen)
    race_screen = RaceScreen(screen)
    play_screen = PlayingScreen(screen)
  

    running = True

    # Main Game Loop
   
    while running:
        dt = min(clock.tick(config.FPS) / 1000.0, 0.1)
     
        # Phase 1: Event Handling
   
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                break

            if current_state == config.STATE_MENU:
                next_state = menu_screen.handle_event(event)
                if next_state == "QUIT":
                    running = False
                    break
                elif next_state:
                    if next_state == config.STATE_PLAYING:
                        play_screen.reset()
                    current_state = next_state
            elif current_state == config.STATE_RACE:
                next_state = race_screen.handle_event(event)
                if next_state:
                    current_state = next_state
            elif current_state == config.STATE_SELECT_SIZE:
               
                pass
            elif current_state == config.STATE_PLAYING:
                next_state = play_screen.handle_event(event)
                if next_state:
                    current_state = next_state
            elif current_state == config.STATE_RESULT:
            
                pass

        
        # Phase 2: State Updates
      
        if current_state == config.STATE_MENU:
            menu_screen.update()
        elif current_state == config.STATE_RACE:
            race_screen.update()
        elif current_state == config.STATE_SELECT_SIZE:
       
            pass
        elif current_state == config.STATE_PLAYING:
            play_screen.update(dt)
        elif current_state == config.STATE_RESULT:
        
            pass


        # Phase 3: Rendering
       
        if current_state == config.STATE_MENU:
            menu_screen.draw()
        elif current_state == config.STATE_RACE:
            race_screen.draw()
        elif current_state == config.STATE_SELECT_SIZE:
            screen.fill(config.COLOR_BG)
          
        elif current_state == config.STATE_PLAYING:
            play_screen.draw(screen)
          
        elif current_state == config.STATE_RESULT:
            screen.fill(config.COLOR_BG)
       

       
        # Phase 4: Display Update
     
        pygame.display.flip()

    
    # Cleanup & Exit
   
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
