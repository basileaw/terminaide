from terminaide import serve_function

def main():
    from chatline import Interface
    
    # Start chatline
    chat = Interface()
    chat.preface("Welcome to the Demo", title="My App", border_color="green")
    chat.start()

if __name__ == "__main__":
    serve_function(main, title="Chatline")