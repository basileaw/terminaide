# terminaide/demos/pong.py

import curses, random, signal, sys

_stdscr=None
exit_requested=False

def pong(stdscr):
    global _stdscr
    _stdscr=stdscr
    signal.signal(signal.SIGINT,handle_exit)
    setup_terminal(stdscr)
    my,mx=stdscr.getmaxyx()
    ph,pw=my-2,mx-2
    ls=rs=0
    high=0
    while True:
        if exit_requested:
            cleanup();return
        ls,rs,winner=run_game(stdscr,my,mx,ph,pw,ls,rs,high)
        if exit_requested:
            cleanup();return
        cur_score=max(ls,rs)
        high=max(high,cur_score)
        if show_game_over(stdscr,ls,rs,high,my,mx,winner):
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

def run_game(stdscr,my,mx,ph,pw,ls,rs,high):
    global exit_requested
    speed=80
    inc=5
    min_spd=40
    win=curses.newwin(ph+2,pw+2,0,0)
    win.keypad(True)
    win.timeout(speed)
    pad_h=5
    pad_w=1
    lpy=ph//2-pad_h//2
    rpy=ph//2-pad_h//2
    lpx=2
    rpx=pw-3
    by=ph//2
    bx=pw//2
    bdy=random.choice([-1,1])
    bdx=random.choice([-1,1])
    winner=None
    draw_screen(stdscr,win,lpy,rpy,lpx,rpx,pad_h,by,bx,ls,rs,high,mx)
    while True:
        if exit_requested:cleanup();return ls,rs,winner
        key=win.getch()
        if key in(ord('q'),27):
            cleanup();return ls,rs,winner
        if key in[curses.KEY_UP,ord('w'),ord('W')]and lpy>0:lpy-=1
        elif key in[curses.KEY_DOWN,ord('s'),ord('S')]and lpy+pad_h<ph:lpy+=1
        if key==ord('1'):
            if bdx>0:
                ideal=by-pad_h//2
                if rpy<ideal and rpy+pad_h<ph:rpy+=1
                elif rpy>ideal and rpy>0:rpy-=1
        else:
            if key in[ord('i'),ord('I')]and rpy>0:rpy-=1
            elif key in[ord('k'),ord('K')]and rpy+pad_h<ph:rpy+=1
        by+=bdy
        bx+=bdx
        if by<=0:
            by=1
            bdy=abs(bdy)
        elif by>=ph-1:
            by=ph-2
            bdy=-abs(bdy)
        if bx<=0:
            rs+=1
            bx,by=pw//2,ph//2
            bdx=1
            bdy=random.choice([-1,1])
            speed=80
            win.timeout(speed)
            if rs>=11:
                winner="right";break
        elif bx>=pw-1:
            ls+=1
            bx,by=pw//2,ph//2
            bdx=-1
            bdy=random.choice([-1,1])
            speed=80
            win.timeout(speed)
            if ls>=11:
                winner="left";break
        if(bx==lpx+pad_w and lpy<=by<lpy+pad_h):
            bdx=abs(bdx)
            pc=lpy+pad_h//2
            off=by-pc
            bdy=off//2
            if speed>min_spd:
                speed-=inc
                win.timeout(speed)
        if(bx==rpx-1 and rpy<=by<rpy+pad_h):
            bdx=-abs(bdx)
            pc=rpy+pad_h//2
            off=by-pc
            bdy=off//2
            if speed>min_spd:
                speed-=inc
                win.timeout(speed)
        draw_screen(stdscr,win,lpy,rpy,lpx,rpx,pad_h,by,bx,ls,rs,high,mx)
    return ls,rs,winner

def draw_screen(stdscr,win,ly,ry,lx,rx,h,by,bx,ls,rs,hi,mx):
    win.erase()
    draw_border(win)
    try:win.addch(by+1,bx+1,ord('*'),curses.color_pair(3)|curses.A_BOLD)
    except:curses.error
    try:
        for i in range(h):
            win.addch(ly+i+1,lx+1,ord('|'),curses.color_pair(1)|curses.A_BOLD)
        for i in range(h):
            win.addch(ry+i+1,rx+1,ord('|'),curses.color_pair(2)|curses.A_BOLD)
    except:curses.error
    draw_score(stdscr,ls,rs,hi,mx)
    stdscr.noutrefresh()
    win.noutrefresh()
    curses.doupdate()

def draw_border(win):
    win.box()
    title="PLAY PONG"
    w=win.getmaxyx()[1]
    if w>len(title)+4:
        win.addstr(0,(w-len(title))//2,title,curses.A_BOLD|curses.color_pair(5))

def draw_score(stdscr,ls,rs,hi,mx):
    stdscr.addstr(0,0," "*mx)
    stdscr.addstr(0,2,f" Left: {ls} ",curses.color_pair(5)|curses.A_BOLD)
    stdscr.addstr(0,mx-14,f" Right: {rs} ",curses.color_pair(5)|curses.A_BOLD)
    ht=f" High: {hi} "
    stdscr.addstr(0,(mx-len(ht))//2,ht,curses.color_pair(5)|curses.A_BOLD)

def show_game_over(stdscr,ls,rs,hi,my,mx,winner):
    stdscr.clear();cy=my//2
    wt="Left Player Wins!"if winner=="left"else"Right Player Wins!"
    data=[
        ("GAME OVER",-3,curses.A_BOLD|curses.color_pair(3)),
        (wt,-1,curses.A_BOLD|curses.color_pair(5)),
        (f"Left Score: {ls} | Right Score: {rs}",0,curses.color_pair(5)),
        (f"High Score: {hi}",1,curses.color_pair(5)),
        ("Press 'r' to restart",3,0),
        ("Press 'q' to quit",4,0),
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
            msg="Thanks for playing Pong!"
            print("\033[2;{}H{}".format((cols-len(msg))//2,msg))
            print("\033[3;{}H{}".format((cols-len("Goodbye!"))//2,"Goodbye!"))
            sys.stdout.flush()
        except:pass

def handle_exit(sig,frame):
    global exit_requested
    exit_requested=True

def run_demo():
    try:
        curses.wrapper(pong)
    except Exception as e:
        print(f"\n\033[31mError: {e}\033[0m")
    finally:
        cleanup()

if __name__=="__main__":
    print("\033[?25l\033[2J\033[H",end="")
    try:
        curses.wrapper(pong)
    finally:
        cleanup()
