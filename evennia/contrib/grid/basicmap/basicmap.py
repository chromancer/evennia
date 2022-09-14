"""
Basic Map - helpme 2022

This adds an ascii `map` to a given room which can be viewed with the `map` command.
You can easily alter it to add special characters, room colors etc.

If you don't expect the map to be updated frequently, you could choose to save the
calculated map as a .ndb value on the room and render that instead of running mapping
calculations anew each time.

This ignores non-ordinal exits (i.e. exits must be compass directions or up/down to be
shown on the map).

An example map:
```
       |
     -[-]-
       |
       |
-[-]--[-]--[-]--[-]
  |    |    |    |
       |    |    |
     -[-]--[-]  [-]
       | \/ |    |
     \ | /\ |
     -[-]--[-]
```

Installation:

Adding the `BasicMapCmdSet` to the default character cmdset will add the `map` command.

Specifically, in `mygame/commands/default_cmdsets.py`:

```
...
from evennia.contrib.grid.basicmap import basicmap  # <---

class CharacterCmdset(default_cmds.Character_CmdSet):
    ...
    def at_cmdset_creation(self):
        ...
        self.add(basicmap.BasicMapCmdSet)  # <---

```

Then `reload` to make the new commands available.

Additional Settings:

In order to change your default map size, you can add to `mygame/server/settings.py`:

BASIC_MAP_SIZE = 5

This changes the default map width/height. 2-5 for most clients is sensible.

If you don't want the player to be able to specify the size of the map, ignore any
arguments passed into the Map command.
"""
import time
from django.conf import settings
from evennia import CmdSet
from evennia.commands.default.muxcommand import MuxCommand

_BASIC_MAP_SIZE = settings.BASIC_MAP_SIZE if hasattr(settings, 'BASIC_MAP_SIZE') else 2

# _COMPASS_DIRECTIONS specifies which way to move the pointer on the x/y axes and what characters to use to depict the exits on the map.
_COMPASS_DIRECTIONS = {
    'north': (0, -3, ' | '),
    'south': (0, 3, ' | '),
    'east': (3, 0, '-'),
    'west': (-3, 0, '-'),
    'northeast': (3, -3, '/'),
    'northwest': (-3, -3, '\\'),
    'southeast': (3, 3, '\\'),
    'southwest': (-3, 3, '/'),
    'up': (0, 0, '^'),
    'down': (0, 0, 'v')
}


class Map(object):
    def __init__(self, caller, size=_BASIC_MAP_SIZE, location=None):
        self.start_time = time.time()
        self.caller = caller
        self.max_width = int(size * 2 + 1) * 5   # This must be an odd number
        self.max_length = int(size * 2 + 1) * 3  # This must be an odd number
        self.has_mapped = {}
        self.curX = None
        self.curY = None
        self.size = size
        self.location = location or caller.location

    def create_grid(self):
        # Create an empty grid of the configured size
        board = []
        for row in range(self.max_length):
            board.append([])
            for column in range(int(self.max_width/5)):
                board[row].extend([' ', '   ', ' '])
        return board

    def exit_name_as_ordinal(self, ex):
        exit_name = ex.name
        if exit_name not in _COMPASS_DIRECTIONS:
            compass_aliases = [direction in ex.aliases.all() for direction in _COMPASS_DIRECTIONS.keys()]
            if compass_aliases[0]:
                exit_name = compass_aliases[0]
            if exit_name not in _COMPASS_DIRECTIONS:
                return ''
        return exit_name

    def update_pos(self, room, exit_name):
        # Update the pointer
        self.curX, self.curY = self.has_mapped[room][0], self.has_mapped[room][1]

        # Move the pointer depending on which direction the exit lies
        # exit_name has already been validated as an ordinal direction at this point
        self.curY += _COMPASS_DIRECTIONS[exit_name][0]
        self.curX += _COMPASS_DIRECTIONS[exit_name][1]

    def has_drawn(self, room):
        return True if room in self.has_mapped.keys() else False

    def draw_room_on_map(self, room, max_distance):
        self.draw(room)
        self.draw_exits(room)

        if max_distance == 0:
            return

        # Check if the caller has access to the room in question. If not, don't draw it.
        # Additionally, if the name of the exit is not ordinal but an alias of it is, use that.
        for ex in [x for x in room.exits if x.access(self.caller, "traverse")]:
            ex_name = self.exit_name_as_ordinal(ex)
            if not ex_name or ex_name in ['up', 'down']:
                continue
            if self.has_drawn(ex.destination):
                continue

            self.update_pos(room, ex_name.lower())
            self.draw_room_on_map(ex.destination, max_distance - 1)

    def draw_exits(self, room):
        x, y = self.curX, self.curY
        for ex in room.exits:
            ex_name = self.exit_name_as_ordinal(ex)

            if not ex_name:
                continue

            ex_character = _COMPASS_DIRECTIONS[ex_name][2]
            delta_x = int(_COMPASS_DIRECTIONS[ex_name][1]/3)
            delta_y = int(_COMPASS_DIRECTIONS[ex_name][0]/3)

            # Make modifications if the exit has BOTH up and down exits
            if ex_name == 'up':
                if 'v' in self.grid[x][y]:
                    self.render_room(room, x, y, p1='^', p2='v')
                else:
                    self.render_room(room, x, y, here='^')
            elif ex_name == 'down':
                if '^' in self.grid[x][y]:
                    self.render_room(room, x, y, p1='^', p2='v')
                else:
                    self.render_room(room, x, y, here='v')
            else:
                self.grid[x + delta_x][y + delta_y] = ex_character

    def draw(self, room):
        # draw initial caller location on map first!
        if room == self.location:
            self.start_loc_on_grid(room)
            self.has_mapped[room] = [self.curX, self.curY]
        else:
            # map all other rooms
            self.has_mapped[room] = [self.curX, self.curY]
            self.render_room(room, self.curX, self.curY)

    def render_room(self, room, x, y, p1='[', p2=']', here=None):
        # Note: This is where you would set colors, symbols etc.
        # Render the room
        you = list("[ ]")

        you[0] = f"{p1}|n"
        you[1] = f"{here if here else you[1]}"
        if room == self.caller.location:
            you[1] = '|[x|co|n'  # Highlight the location you are currently in
        you[2] = f"{p2}|n"

        self.grid[x][y] = "".join(you)

    def start_loc_on_grid(self, room):
        x = int((self.max_width * 0.6 - 1) / 2)
        y = int((self.max_length - 1) / 2)

        self.render_room(room, x, y)
        self.curX, self.curY = x, y

    def show_map(self, debug=False):
        map_string = ""
        self.grid = self.create_grid()
        self.draw_room_on_map(self.location, self.size)

        for row in self.grid:
            map_row = "".join(row)
            if map_row.strip() != "":
                map_string += f"{map_row}\n"

        elapsed = time.time() - self.start_time
        if debug:
            map_string += f"\nTook {elapsed}ms to render the map.\n"

        return "%s" % map_string


class CmdMap(MuxCommand):
    """
    Check the local map around you.

    Usage: map (optional size)
    """
    key = "map"

    def func(self):
        size = _BASIC_MAP_SIZE
        if self.args.isnumeric():
            size = int(self.args)

        # You can run show_map(debug=True) to see how long it takes.
        map_here = Map(self.caller, size=size).show_map()
        self.caller.msg((map_here, {"type": "map"}))


# CmdSet for easily install all commands
class BasicMapCmdSet(CmdSet):
    """
    The map command.
    """

    def at_cmdset_creation(self):
        self.add(CmdMap)
