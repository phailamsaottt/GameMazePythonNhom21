import sys
import pygame
import config

from menu import MenuScreen, NameInputScreen, SelectSizeScreen, SoloSetupScreen
from race import TwoPlayerScreen
from play import PlayingScreen
from leaderboard import LeaderboardScreen


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
    pygame.display.set_caption(config.GAME_TITLE)
    clock = pygame.time.Clock()


    current_state = config.STATE_MENU

  
    menu_screen = MenuScreen(screen)
    select_size_screen = SelectSizeScreen(screen)
    solo_setup_screen: SoloSetupScreen | None = None
    name_input_screen = NameInputScreen(screen)
    two_player_screen: TwoPlayerScreen | None = None
    leaderboard_screen = LeaderboardScreen(screen)
    play_screen: PlayingScreen | None = None

    running = True

    # Main Game Loop
   
    while running:
        dt = min(clock.tick(config.FPS) / 1000.0, 0.1)
     
        # 1: Event 
   
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
                    if next_state == config.STATE_RESULT:
                        leaderboard_screen.refresh()
                    current_state = next_state
            elif current_state == config.STATE_SELECT_SIZE:
                next_state = select_size_screen.handle_event(event)
                if next_state == config.STATE_SOLO_SETUP:
                    if select_size_screen.selected_size is None:
                        continue
                    solo_setup_screen = SoloSetupScreen(screen, select_size_screen.selected_size)
                    current_state = config.STATE_SOLO_SETUP
                elif next_state:
                    current_state = next_state
            elif current_state == config.STATE_SOLO_SETUP:
                if solo_setup_screen is None:
                    current_state = config.STATE_SELECT_SIZE
                    continue
                next_state = solo_setup_screen.handle_event(event)
                if next_state == config.STATE_PLAYING:
                    if solo_setup_screen.selected_name is None or solo_setup_screen.selected_character_id is None:
                        continue
                    rows, cols = solo_setup_screen.maze_size
                    play_screen = PlayingScreen(
                        screen,
                        rows=rows,
                        cols=cols,
                        player_name=solo_setup_screen.selected_name,
                        character_id=solo_setup_screen.selected_character_id,
                    )
                    current_state = config.STATE_PLAYING
                elif next_state:
                    current_state = next_state
            elif current_state == config.STATE_NAME_INPUT:
                next_state = name_input_screen.handle_event(event)
                if next_state == config.STATE_RACE:
                    names = name_input_screen.selected_names or ("Player 1", "Player 2")
                    two_player_screen = TwoPlayerScreen(
                        screen,
                        player1_name=names[0],
                        player2_name=names[1],
                    )
                    current_state = config.STATE_RACE
                elif next_state:
                    current_state = next_state
            elif current_state == config.STATE_RACE:
                if two_player_screen is None:
                    current_state = config.STATE_MENU
                    continue
                next_state = two_player_screen.handle_event(event)
                if next_state:
                    current_state = next_state
            elif current_state == config.STATE_PLAYING:
                if play_screen is None:
                    current_state = config.STATE_MENU
                    continue
                next_state = play_screen.handle_event(event)
                if next_state:
                    current_state = next_state
            elif current_state == config.STATE_RESULT:
                next_state = leaderboard_screen.handle_event(event)
                if next_state:
                    current_state = next_state

        
        # 2: State Updates
      
        if current_state == config.STATE_MENU:
            menu_screen.update()
        elif current_state == config.STATE_SELECT_SIZE:
            select_size_screen.update()
        elif current_state == config.STATE_SOLO_SETUP:
            if solo_setup_screen is not None:
                solo_setup_screen.update()
        elif current_state == config.STATE_NAME_INPUT:
            name_input_screen.update()
        elif current_state == config.STATE_RACE:
            if two_player_screen is not None:
                two_player_screen.update(dt)
        elif current_state == config.STATE_PLAYING:
            if play_screen is not None:
                play_screen.update(dt)
        elif current_state == config.STATE_RESULT:
            leaderboard_screen.update()


        #3: Rendering
       
        if current_state == config.STATE_MENU:
            menu_screen.draw()
        elif current_state == config.STATE_SELECT_SIZE:
            select_size_screen.draw(screen)
        elif current_state == config.STATE_SOLO_SETUP:
            if solo_setup_screen is not None:
                solo_setup_screen.draw(screen)
        elif current_state == config.STATE_NAME_INPUT:
            name_input_screen.draw(screen)
        elif current_state == config.STATE_RACE:
            if two_player_screen is not None:
                two_player_screen.draw()
        elif current_state == config.STATE_PLAYING:
            if play_screen is not None:
                play_screen.draw(screen)
          
        elif current_state == config.STATE_RESULT:
            leaderboard_screen.draw(screen)
       
    #4 update
     
        pygame.display.flip()

    
    # Exit
   
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
