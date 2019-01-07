#this file hasn't been tested / run

"/tmp/moves.csv" <- "/home/jtrigg/Downloads/lichess_db_standard_rated_2018-10.pgn"
    python3 pgn_to_moves.py

"/tmp/filtered_moves.csv" <- "/tmp/moves.csv"
    python3 filter_moves.py

 <- "/tmp/filtered_moves.csv"
    python3 opening_book.py