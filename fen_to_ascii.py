import sys

import chess


board = chess.Board(sys.argv[1])

if len(sys.argv) > 2:
    move = sys.argv[2]
    board.push(chess.Move.from_uci(move))
    print(board.fen())
    
print(board)
