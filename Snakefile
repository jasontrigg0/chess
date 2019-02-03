#this file hasn't been tested / run

PGN_FILE="/home/jtrigg/Downloads/lichess_db_standard_rated_2018-10.pgn"
PGN_FILE="/home/jtrigg/files/misc/KingBase2018-all.pgn"

#read PGN_FILE
"/tmp/moves.csv" <- PGN_FILE
    python3 pgn_to_moves.py


####opening book####

#filter moves for opening book
"/tmp/filtered_moves.csv" <- "/tmp/moves.csv"
    python3 filter_moves.py

#generate opening book
"%book" <- "/tmp/filtered_moves.csv"
    python3 opening_book.py



####move predictions####

#create rows for move prediction / analysis
"/tmp/pred_data.csv" <- "/tmp/moves.csv"
    python3 generate_prediction_data.py

#create features for prediction
"/tmp/chess_features.csv" <- "/tmp/pred_data.csv"
    python3 compute_features.py

#generate prediction
"%regression" <- "/tmp/chess_features.csv"
    less /tmp/chess_features.csv | pcsv -p 'r["abs_eval"] = abs(int(r["eval"]))' | pcsv -p 'r["best_move"] = 1* ( r["loss"] == "0" )' | linreg -c elo,abs_eval -t loss
    less /tmp/chess_features.csv | pcsv -p 'r["abs_eval"] = abs(int(r["eval"]))' | pcsv -p 'r["best_move"] = 1* ( r["loss"] == "0" )' | linreg -c loss,best_move -t elo