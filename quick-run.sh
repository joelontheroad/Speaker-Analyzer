# Run all reports
./speaker-analyzer.py --report --mask  --connector Austin 
./speaker-analyzer.py --report --mask  --connector Houston
./speaker-analyzer.py --report  --connector Houston
./argument-analyzer.py --connector Houston
./argument-analyzer.py --connector Austin


# Run  indexer
./knowledge-indexer.py --force --connector Austin

./knowledge-indexer.py --force --connector Houston

