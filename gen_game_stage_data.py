#https://github.com/niklasf/python-chess
import chess
import chess.pgn
import chess.engine
import csv



if __name__ == "__main__":
    STOCKFISH_BINARY="/files/install/Stockfish/src/stockfish"
    pgn_file = "/home/jason/Downloads/Caissabase_2022_12_24/caissabase.pgn"
    pgn = open(pgn_file, errors="replace")

    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_BINARY)


    f_out = open("/tmp/chess.csv",'w')
    writer = csv.DictWriter(f_out,fieldnames=["date","event","white_name","white_fide","white_elo","black_name","black_fide","black_elo","opening_eval","midgame_eval","result"])
    writer.writeheader()


    # pull list of events where players play multiple games in the same day
    # these are likely not classical, also pull the list where they play one
    # game per day -> probably are classical
    player_date_events = {}

    #scan for 2600+ games
    selected_game_offsets = []
    cnt = 0


    while True:
        cnt += 1
        offset = pgn.tell()

        headers = chess.pgn.read_headers(pgn)
        if headers is None:
            break

        white = headers["White"]
        black = headers["Black"]
        dt = headers["Date"]
        event = headers["Event"]
        player_date_events.setdefault((white,dt,event),0)
        player_date_events[(white,dt,event)] += 1
        player_date_events.setdefault((black,dt,event),0)
        player_date_events[(black,dt,event)] += 1
        if cnt > 1000000:
            break

    event_to_counts = {}
    for key in player_date_events:
        event = key[2]
        event_to_counts.setdefault(key[2],{"single":0,"multiple":0})
        cnt = player_date_events[key]
        if cnt > 1:
            event_to_counts[key[2]]["multiple"] += 1
        elif cnt == 1:
            event_to_counts[key[2]]["single"] += 1
        else:
            raise

    for event in event_to_counts:
        print(event)
        print(event_to_counts[event])

    #raise Exception("testing123")

    while True:
        offset = pgn.tell()

        headers = chess.pgn.read_headers(pgn)
        if headers is None:
            break

        skip_names = [
            "SpeedChess",
            "Rapid",
            "Blitz",
            "13th Hainan Danzhou GM", #rapid
            "Titled Tue", #blitz
            "MrDodgy Inv", #blitz
            "TCEC", #computer
            "Meltwater Tour Final", #rapid
            "Region Group Cup 2022", #rapid
            "World Fischer Random",
            "CGC KO", #rapid
            "13th World Teams", #rapid, maybe previous versions were classical
            "SCO National Chess Online", #rounds one hour apart = blitz?
            "Julius Baer GenCup", #rapid
            "FTX Crypto Cup", #rapid
            "Chessable Masters", #rapid
            "Norway Armageddon", #Nth Norway Armageddon
            "Salamanca Uni Masters", #rapid
            "Champ Showdown 9LX", #Fischer random
            "Chess.com RCC", #rapid
            "FTX Road to Miami",
            "chess.com Junior Speed",
            "Oslo Esports Cup", #rapid
            "Charity Cup",
            "Airthings Masters",
            "Solidarity NOR-UKR Match", #rapid
            #TODO: why only three games from the 2021 world championship
            #TODO: remove World Cup tiebreak matches
            "San Fermin Masters", #blitz
            "Goldmoney Asian", #rapid
            "Katara Bullet Final",
            "NIC Classic", #rapid
            "DM Carlsen-Dubov",
            "DM Carlsen-Artemiev",
            "Carlsen vs. Challengers", #blitz
            "Titled Arena",
            "Magnus Carlsen Inv", #rapid
            "Magnus-Alireza 27th Feb",
            "Carlsen-Tang Bullet",
            "Magnus-Alireza Bullet",
            "chess.com Speed",
            "Chess24 Banter",
            "Carlsen Tour Final", #rapid
            "Legends of Chess", #rapid
            "Clutch Chess Showdown", #rapid
            "Lindores Abbey", #rapid
            "FIDE Steinitz Mem",
            "Carlsen Inv",
            #TODO: 11th London Classic pick out the classical games
            "Carlsen-Ding Showdown",
            "PRO League",
            #TODO: remove rapid games from American Cup: https://uschesschamps.com/2022-american-cup-recap/2022-american-cup-day-2-recap
            "ch-USA TB", #tiebreaks
            "Clutch Champions Showdown",
            "Chessbrah Inv",
            "Online Nations Cup", #rapid
            #TODO: remove London Classic rapid and blitz games
            "Sinquefield GCT TB",
        ]
        if any(x in headers["Event"] for x in skip_names): continue

        if int(headers.get("WhiteElo",0)) > 2600 or int(headers.get("BlackElo",0)) > 2600:
            cnt += 1
            selected_game_offsets.append(offset)

        if cnt > 150000:
            break

    print(selected_game_offsets)

    for offset in selected_game_offsets:
        print(offset)
        pgn.seek(offset)
        game = chess.pgn.read_game(pgn)

        game_result = {
            "0-1": 0,
            "1/2-1/2":0.5,
            "1-0":1,
            "*":None
        }[game.headers["Result"]]

        print(game.headers)
        row = {
            "date": game.headers["Date"],
            "event": game.headers["Event"],
            "white_name": game.headers["White"],
            "white_fide": game.headers.get("WhiteFideId",""),
            "white_elo": game.headers.get("WhiteElo",""),
            "black_name": game.headers["Black"],
            "black_fide": game.headers.get("BlackFideId",""),
            "black_elo": game.headers.get("BlackElo",""),
            "opening_eval": "",
            "midgame_eval": "",
            "result": game_result
        }

        board = game.board()

        def get_score():
            info = engine.analyse(board, chess.engine.Limit(time=0.1))
            mate = info["score"].relative.mate()
            if mate is not None:
                if mate > 0:
                    return 10
                elif mate < 0:
                    return -10
            else:
                cp = info["score"].relative.score()
                return cp / 100

        for i,move in enumerate(game.mainline_moves()):
            board.push(move)
            if i == 39:
                #position after 20 moves each
                row["opening_eval"] = get_score()
            elif i == 79:
                #position after 40 moves each
                row["midgame_eval"] = get_score()
        writer.writerow(row)
        f_out.flush()
    print("done")
    exit()
