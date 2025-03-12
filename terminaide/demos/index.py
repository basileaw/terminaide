# terminaide/demos/index.py

import curses, signal, sys

_stdscr=None
_exit_requested=False

def handle_exit(sig,frame):
    global _exit_requested
    _exit_requested=True

def cleanup():
    if _stdscr:
        try:
            curses.endwin()
            print("\033[?25l\033[2J\033[H",end="")
            try:rows,cols=_stdscr.getmaxyx()
            except:rows,cols=24,80
            msg="Thank you for using terminaide"
            print("\033[2;{}H{}".format((cols-len(msg))//2,msg))
            print("\033[3;{}H{}".format((cols-len("Goodbye!"))//2,"Goodbye!"))
            sys.stdout.flush()
        except:pass

def safe_addstr(stdscr,y,x,text,attr=0):
    h,w=stdscr.getmaxyx()
    if y<0 or y>=h or x<0 or x>=w:return
    ml=w-x
    if ml<=0:return
    t=text[:ml]
    try:stdscr.addstr(y,x,t,attr)
    except:curses.error

def draw_horizontal_line(stdscr,y,x,width,attr=0):
    for i in range(width):
        safe_addstr(stdscr,y,x+i," ",attr)

def index_menu(stdscr):
    global _stdscr
    _stdscr=stdscr
    signal.signal(signal.SIGINT,handle_exit)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1,curses.COLOR_BLUE,-1)
    curses.init_pair(2,curses.COLOR_WHITE,-1)
    curses.init_pair(3,curses.COLOR_CYAN,-1)
    curses.init_pair(4,curses.COLOR_BLACK,curses.COLOR_CYAN)
    curses.init_pair(5,curses.COLOR_BLACK,curses.COLOR_WHITE)
    curses.init_pair(6,curses.COLOR_GREEN,-1)
    curses.curs_set(0)
    stdscr.clear()
    options=["Snake","Tetris","Pong"]
    co=0
    po=0
    stdscr.clear()
    my,mx=stdscr.getmaxyx()
    title_lines=[
"████████╗███████╗██████╗ ███╗   ███╗██╗███╗   ██╗      █████╗ ██████╗  ██████╗ █████╗ ██████╗ ███████╗",
"╚══██╔══╝██╔════╝██╔══██╗████╗ ████║██║████╗  ██║     ██╔══██╗██╔══██╗██╔════╝██╔══██╗██╔══██╗██╔════╝",
"   ██║   █████╗  ██████╔╝██╔████╔██║██║██╔██╗ ██║     ███████║██████╔╝██║     ███████║██║  ██║█████╗  ",
"   ██║   ██╔══╝  ██╔══██╗██║╚██╔╝██║██║██║╚██╗██║     ██╔══██║██╔══██╗██║     ██╔══██║██║  ██║██╔══╝  ",
"   ██║   ███████╗██║  ██║██║ ╚═╝ ██║██║██║ ╚████║     ██║  ██║██║  ██║╚██████╗██║  ██║██████╔╝███████╗",
"   ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝     ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚═════╝ ╚══════╝"
    ]
    simple_title_lines=[
 " _____              _         _                   _      ",
 "|_   _|__ _ __ _ __ (_)_ __   /_\\  _ __ ___ __ _  _| | ___ ",
 "  | |/ _ \\ '__| '_ \\| | '_ \\ //_\\\\| '__/ __/ _` |/ _` |/ _ \\",
 "  | |  __/ |  | | | | | | | /  _ \\ | | (_| (_| | (_| |  __/",
 "  |_|\\___|_|  |_| |_|_|_| |_\\_/ \\_\\_|  \\___\\__,_|\\__,_|\\___|"
    ]
    very_simple_title=[
 "==============================",
 "||     TERMIN-ARCADE       ||",
 "=============================="
    ]
    if mx>=90:title_to_use=title_lines
    elif mx>=60:title_to_use=simple_title_lines
    else:title_to_use=very_simple_title
    for i,line in enumerate(title_to_use):
        if len(line)<=mx:
            safe_addstr(stdscr,1+i,(mx-len(line))//2,line,curses.color_pair(1)|curses.A_BOLD)
    sy=2+len(title_to_use)
    instr="Use ↑/↓ to navigate, Enter to select, Q to quit"
    safe_addstr(stdscr,sy+2,(mx-len(instr))//2,instr,curses.color_pair(2))
    mol=max(len(o)for o in options)
    oy=sy+5
    for i,o in enumerate(options):
        st=curses.color_pair(5)if i==co else curses.color_pair(4)
        pad=" "*3
        sp=mol-len(o)
        ls=sp//2
        rs=sp-ls
        bt=f"{pad}{' '*ls}{o}{' '*rs}{pad}"
        safe_addstr(stdscr,oy+i*2,(mx-len(bt))//2,bt,st|curses.A_BOLD)
    while True:
        if _exit_requested:break
        if co!=po:
            st=curses.color_pair(4)|curses.A_BOLD
            sp=mol-len(options[po])
            ls=sp//2
            rs=sp-ls
            pbt=f"{' '*3}{' '*ls}{options[po]}{' '*rs}{' '*3}"
            safe_addstr(stdscr,oy+po*2,(mx-len(pbt))//2,pbt,st)
            st=curses.color_pair(5)|curses.A_BOLD
            sp=mol-len(options[co])
            ls=sp//2
            rs=sp-ls
            nbt=f"{' '*3}{' '*ls}{options[co]}{' '*rs}{' '*3}"
            safe_addstr(stdscr,oy+co*2,(mx-len(nbt))//2,nbt,st)
            po=co
        stdscr.refresh()
        try:
            k=stdscr.getch()
            if k in[ord('q'),ord('Q'),27]:break
            elif k==curses.KEY_UP and co>0:co-=1
            elif k==curses.KEY_DOWN and co<len(options)-1:co+=1
            elif k in[curses.KEY_ENTER,ord('\n'),ord('\r')]:
                if co==0:return"snake"
                elif co==1:return"tetris"
                elif co==2:return"pong"
        except KeyboardInterrupt:break
    return"exit"

def run_demo():
    try:
        choice=curses.wrapper(index_menu)
        if choice=="exit":
            cleanup();return
        if _stdscr:curses.endwin()
        if choice=="snake":
            from terminaide.demos import play_snake
            play_snake()
        elif choice=="tetris":
            from terminaide.demos import play_tetris
            play_tetris()
        elif choice=="pong":
            from terminaide.demos import play_pong
            play_pong()
    except Exception as e:
        print(f"\n\033[31mError in index demo: {e}\033[0m")
    finally:
        if choice=="exit":
            cleanup()

if __name__=="__main__":
    print("\033[?25l\033[2J\033[H",end="")
    try:
        curses.wrapper(index_menu)
    finally:
        cleanup()