# terminaide/demos/snake.py

import curses, random, signal, sys
from collections import deque

_stdscr=None
_exit_requested=False

def snake(stdscr):
    global _stdscr
    _stdscr=stdscr
    signal.signal(signal.SIGINT,handle_exit)
    setup_terminal(stdscr)
    max_y,max_x=stdscr.getmaxyx()
    ph,pw=max_y-2,max_x-2
    high_score=0
    while True:
        if _exit_requested:
            cleanup();return
        score=run_game(stdscr,max_y,max_x,ph,pw,high_score)
        if _exit_requested:
            cleanup();return
        high_score=max(high_score,score)
        if show_game_over(stdscr,score,high_score,max_y,max_x):
            break

def setup_terminal(stdscr):
    curses.curs_set(0)
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)
    curses.use_env(False)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1,curses.COLOR_GREEN,-1)
    curses.init_pair(2,curses.COLOR_CYAN,-1)
    curses.init_pair(3,curses.COLOR_RED,-1)
    curses.init_pair(4,curses.COLOR_WHITE,-1)
    curses.init_pair(5,curses.COLOR_YELLOW,-1)

def run_game(stdscr,my,mx,ph,pw,high_score=0):
    global _exit_requested
    score=0
    speed=100
    win=curses.newwin(ph+2,pw+2,0,0)
    win.keypad(True)
    win.timeout(speed)
    s=deque([(ph//2,pw//4)])
    direction=curses.KEY_RIGHT
    food=new_food(s,ph,pw)
    draw_screen(stdscr,win,s,food,score,high_score,mx)
    while True:
        if _exit_requested:cleanup();return score
        key=win.getch()
        if key in (ord('q'),27):cleanup();return score
        new_dir=process_input(key,direction)
        if new_dir:direction=new_dir
        hy,hx=s[0]
        nh=move_head(hy,hx,direction)
        if is_collision(nh,s,ph,pw):break
        s.appendleft(nh)
        if nh==food:
            score+=10
            if speed>50:
                speed=max(50,speed-3)
                win.timeout(speed)
            food=new_food(s,ph,pw)
        else:
            s.pop()
        draw_screen(stdscr,win,s,food,score,high_score,mx)
    return score

def draw_screen(stdscr,win,snake,food,score,high_score,mx):
    win.erase()
    draw_border(win)
    try:win.addch(food[0]+1,food[1]+1,ord('*'),curses.color_pair(3)|curses.A_BOLD)
    except:curses.error
    draw_snake(win,snake)
    draw_score(stdscr,score,high_score,mx)
    stdscr.noutrefresh()
    win.noutrefresh()
    curses.doupdate()

def draw_border(win):
    win.box()
    title="PLAY SNAKE"
    w=win.getmaxyx()[1]
    if w>len(title)+4:
        win.addstr(0,(w-len(title))//2,title,curses.A_BOLD|curses.color_pair(5))

def draw_snake(win,snake):
    try:
        y,x=snake[0]
        win.addch(y+1,x+1,ord('O'),curses.color_pair(1)|curses.A_BOLD)
        for y,x in list(snake)[1:]:
            win.addch(y+1,x+1,ord('o'),curses.color_pair(2))
    except:curses.error

def draw_score(stdscr,score,high_score,mx):
    stdscr.addstr(0,0," "*mx)
    stdscr.addstr(0,2,f" Score: {score} ",curses.color_pair(5)|curses.A_BOLD)
    txt=f" High Score: {high_score} "
    stdscr.addstr(0,mx-len(txt)-2,txt,curses.color_pair(5)|curses.A_BOLD)

def process_input(key,cur_dir):
    if key in[curses.KEY_UP,ord('w'),ord('W')]and cur_dir!=curses.KEY_DOWN:return curses.KEY_UP
    if key in[curses.KEY_DOWN,ord('s'),ord('S')]and cur_dir!=curses.KEY_UP:return curses.KEY_DOWN
    if key in[curses.KEY_LEFT,ord('a'),ord('A')]and cur_dir!=curses.KEY_RIGHT:return curses.KEY_LEFT
    if key in[curses.KEY_RIGHT,ord('d'),ord('D')]and cur_dir!=curses.KEY_LEFT:return curses.KEY_RIGHT

def move_head(y,x,d):
    if d==curses.KEY_UP:return(y-1,x)
    if d==curses.KEY_DOWN:return(y+1,x)
    if d==curses.KEY_LEFT:return(y,x-1)
    return(y,x+1)

def is_collision(head,snake,h,w):
    y,x=head
    if y<0 or y>=h or x<0 or x>=w:return True
    if head in list(snake)[1:]:return True
    return False

def new_food(snake,h,w):
    while True:
        fy=random.randint(0,h-1)
        fx=random.randint(0,w-1)
        if(fy,fx)not in snake:return(fy,fx)

def show_game_over(stdscr,score,high_score,my,mx):
    stdscr.clear();cy=my//2
    data=[
        ("GAME OVER",-3,curses.A_BOLD|curses.color_pair(3)),
        (f"Your Score: {score}",-1,curses.color_pair(5)),
        (f"High Score: {high_score}",0,curses.color_pair(5)),
        ("Press 'r' to restart",2,0),
        ("Press 'q' to quit",3,0),
    ]
    for txt,yo,attr in data:
        stdscr.addstr(cy+yo,mx//2-len(txt)//2,txt,attr)
    stdscr.noutrefresh();curses.doupdate()
    stdscr.nodelay(False)
    while True:
        k=stdscr.getch()
        if k==ord('q'):return True
        if k==ord('r'):return False

def cleanup():
    if _stdscr:
        try:
            curses.endwin()
            print("\033[?25l\033[2J\033[H",end="")
            try:rows,cols=_stdscr.getmaxyx()
            except:rows,cols=24,80
            msg="Thanks for playing Snake!"
            print("\033[2;{}H{}".format((cols-len(msg))//2,msg))
            print("\033[3;{}H{}".format((cols-len("Goodbye!"))//2,"Goodbye!"))
            sys.stdout.flush()
        except:pass

def handle_exit(sig,frame):
    global _exit_requested
    _exit_requested=True

def run_demo():
    try:
        curses.wrapper(snake)
    except Exception as e:
        print(f"\n\033[31mError in demo: {e}\033[0m")
    finally:
        cleanup()

if __name__=="__main__":
    print("\033[?25l\033[2J\033[H",end="")
    try:
        curses.wrapper(snake)
    finally:
        cleanup()
