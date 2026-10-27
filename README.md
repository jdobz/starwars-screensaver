# Star Wars ASCII Screensaver

A Star Wars take on the classic [asciiquarium](https://robobunny.com/projects/asciiquarium/html/)
terminal screensaver. Instead of fish, the top of your terminal is a space
battle and the bottom is a desert world full of walkers, droids and heroes.

It is a single Python file with no dependencies beyond the standard library.

<img width="1680" height="1050" alt="image" src="https://github.com/user-attachments/assets/aff84ec7-f54b-490a-8237-ae02f553ab87" />


## Run it

```bash
python3 starwars_screensaver.py
```

Requirements:

- Python 3.8 or newer (it uses the built-in `curses` module)
- macOS or Linux. On Windows, install `windows-curses` first: `pip install windows-curses`
- A terminal at least **60 x 20**. It looks best full screen in a 256-color
  terminal such as iTerm2, since the grays, orange and bright blue need 256
  colors (it falls back to the basic colors otherwise)

Resizing the window rebuilds the scene to fit.

## Controls

| Key | Action |
|-----|--------|
| `q` | Quit |
| `r` | Redraw / rebuild the scene |
| `p` | Pause / resume |
| `s` | Fire the Death Star's superlaser |
| `f` | Fly the Millennium Falcon across |
| `c` | Fly the Razor Crest across |
| `x` | Start the Death Star torpedo run |

Options:

```
--fps N      frames per second (default 15; movement is per frame, so a
             higher value also makes everything faster)
--version    print the version
--help       show help
```

## What's in it

**Space (top 75%)**

- TIE fighters, X-wings and Y-wings in dogfights. X-wings fire red lasers from
  their wing cannons, TIEs fire green, Y-wings fire blue. Fighters that collide
  explode together
- Imperial Star Destroyers with gun turrets that fire green lasers
- The Millennium Falcon (with TIEs chasing) and the Razor Crest
- A Death Star with a charging, firing superlaser
- A very rare event: an X-wing torpedoes the Death Star, it explodes, the screen
  jumps to hyperspace, and the scene resets with a new Death Star
  (press `x` to see it any time)
- Twinkling stars, drifting wreckage, explosions and debris

**Ground (bottom 25%)**

- AT-ATs and AT-STs on the march
- Speeders, C-3PO and R2-D2, Yoda, Ewoks and stormtroopers
- Jedi lightsaber duels and stormtroopers chasing Ewoks
- The Mandalorian and Grogu, and Darth Vader

Big scenes run in two independent chains, one in the sky and one on the
ground, so something is almost always happening in both.

## How it works

The engine follows the same ideas as the original asciiquarium: entities with a
shape, a color mask, a position, a depth for drawing order, a speed, and
callbacks for dying, spawning and collisions. Sprites are drawn facing right and
mirrored automatically for the other direction. Several of the bigger ships
(Star Destroyer, Death Star, Falcon, Razor Crest, AT-AT, AT-ST) are generated
by small builder functions, so the Star Destroyer and Death Star scale with the
size of your terminal.

## Credits

- Inspired by **asciiquarium** by Kirk Baucom. This project shares its idea and
  general structure, but it is a from-scratch Python implementation and does
  not use the original Perl code.
- All art is original, simplified ASCII drawn for this project.

## Disclaimer

This is an unofficial fan project. It is not affiliated with, endorsed by, or
sponsored by Lucasfilm Ltd., The Walt Disney Company, or any other rights
holder. Star Wars and all related names and characters are trademarks of their
respective owners.

## License

[MIT](LICENSE)
