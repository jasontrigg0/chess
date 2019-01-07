#https://github.com/niklasf/python-chess
import chess
import chess.uci
import chess.pgn
import chess.polyglot
import csv

#Read in a pgn list of games and generate a csv of moves

PGN_FILE = "/home/jtrigg/Downloads/lichess_db_standard_rated_2018-10.pgn"
CEREBELLUM_FILE = "/home/jtrigg/Downloads/Cerebellum_light_180611/Cerebellum_Light_Poly.bin"

if __name__ == "__main__":
    pgn = open(PGN_FILE)

    OUTPUT_FILE = "/tmp/moves.csv"
    with open(OUTPUT_FILE, 'w') as csvfile:
        fieldnames = ["zobrist", "start_fen", "previous_moves", "move"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        GAME_CNT = 50000
        #100 games -> 6620 distinct positions
        #1000 games -> 64012 distinct positions
        #10000 games -> 610650 distinct positions
        for i in range(GAME_CNT):
            next_game = chess.pgn.read_game(pgn)
            #print(next_game)
            #print(next_game.headers)
            fields = ["TimeControl", "WhiteElo", "BlackElo", "Move"]
            board = next_game.board()
            previous_moves = []
            for move in next_game.mainline_moves():
                start_position = board.fen()
                zobrist_position = chess.polyglot.zobrist_hash(board)
                board.push(move)
                writer.writerow({"zobrist":zobrist_position, "previous_moves": str(previous_moves), "start_fen":start_position, "move":move})

                previous_moves.append(str(move))

    # not using cerebellum at the moment:

    # board = chess.Board()
    # with chess.polyglot.open_reader(CEREBELLUM_FILE) as reader:
    #     for entry in reader.find_all(board):
    #         print(dir(entry))
    #         print(entry.move(), entry.weight, entry.learn)
