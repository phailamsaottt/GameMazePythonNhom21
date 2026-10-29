import sys
from pathlib import Path
import pygame
import config

from menu import MenuScreen, NameInputScreen, SelectSizeScreen, SoloSetupScreen
from race import TwoPlayerScreen
from play import PlayingScreen
from leaderboard import LeaderboardScreen


def _start_background_music() -> None:
    """Start the gameplay loop without interrupting menu or effect sounds."""
    if not pygame.mixer.get_init():
        try:
            pygame.mixer.init()
        except pygame.error:
            return

    candidates = (
        Path(config.SOUNDS_DIR) / "background.mp3",
        Path(config.BASE_DIR) / "assets" / "sounds" / "background.mp3",
    )
    music_path = next((path for path in candidates if path.is_file()), None)
    if music_path is None:
        return

    try:
        pygame.mixer.music.stop()
        pygame.mixer.music.load(str(music_path))
        pygame.mixer.music.set_volume(getattr(config, "DEFAULT_VOLUME", 0.5))
        pygame.mixer.music.play(-1)
    except pygame.error:
        pass


def _stop_background_music() -> None:
    if pygame.mixer.get_init():
        try:
            pygame.mixer.music.stop()
        except pygame.error:
            pass


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
    pygame.display.set_caption(config.GAME_TITLE)
    clock = pygame.time.Clock()


    current_state = config.STATE_MENU

  
    menu_screen = MenuScreen(screen)
    select_size_screen = SelectSizeScreen(screen)
    race_size_screen = SelectSizeScreen(
        screen,
        next_state=config.STATE_NAME_INPUT,
    )
    solo_setup_screen: SoloSetupScreen | None = None
    name_input_screen = NameInputScreen(
        screen,
        back_state=config.STATE_SELECT_RACE_SIZE,
    )
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
            elif current_state == config.STATE_SELECT_RACE_SIZE:
                next_state = race_size_screen.handle_event(event)
                if next_state == config.STATE_NAME_INPUT:
                    if race_size_screen.selected_size is None:
                        continue
                    current_state = config.STATE_NAME_INPUT
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
                    _start_background_music()
                    current_state = config.STATE_PLAYING
                elif next_state:
                    current_state = next_state
            elif current_state == config.STATE_NAME_INPUT:
                next_state = name_input_screen.handle_event(event)
                if next_state == config.STATE_RACE:
                    if race_size_screen.selected_size is None:
                        current_state = config.STATE_SELECT_RACE_SIZE
                        continue
                    rows, cols = race_size_screen.selected_size
                    names = name_input_screen.selected_names or ("Player 1", "Player 2")
                    two_player_screen = TwoPlayerScreen(
                        screen,
                        player1_name=names[0],
                        player2_name=names[1],
                        rows=rows,
                        cols=cols,
                    )
                    _start_background_music()
                    current_state = config.STATE_RACE
                elif next_state:
                    current_state = next_state
            elif current_state == config.STATE_RACE:
                if two_player_screen is None:
                    current_state = config.STATE_MENU
                    continue
                next_state = two_player_screen.handle_event(event)
                if next_state:
                    if next_state != config.STATE_RACE:
                        _stop_background_music()
                    current_state = next_state
            elif current_state == config.STATE_PLAYING:
                if play_screen is None:
                    current_state = config.STATE_MENU
                    continue
                next_state = play_screen.handle_event(event)
                if next_state:
                    if next_state != config.STATE_PLAYING:
                        _stop_background_music()
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
        elif current_state == config.STATE_SELECT_RACE_SIZE:
            race_size_screen.update()
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
        elif current_state == config.STATE_SELECT_RACE_SIZE:
            race_size_screen.draw(screen)
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
