python3 << 'EOF'
import csv
import pandas as pd

with open('/mnt/user-data/uploads/websocket_stock_values_rows__3_.csv') as f:
    wsv = list(csv.DictReader(f))

df = pd.DataFrame(wsv)
df['ltp'] = pd.to_numeric(df['ltp'])
df['volume'] = pd.to_numeric(df['volume'])
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values(['stock','date']).reset_index(drop=True)

dates = sorted(df['date'].unique())

df['avg_5d_vol'] = df.groupby('stock')['volume'].transform(
    lambda x: x.shift(1).rolling(5, min_periods=2).mean()
)
df['vol_ratio'] = df['volume'] / df['avg_5d_vol']

signal_date = pd.Timestamp('2026-06-29')
blast_date  = pd.Timestamp('2026-06-30')
idx = list(dates).index(signal_date)
prev_dates = dates[idx-3:idx]
prev_day = dates[idx-1]

print(f"Signal date: {signal_date.date()}")
print(f"Prev 3 days: {[str(d.date()) for d in prev_dates]}")
print(f"Prev day: {prev_day.date()}")
print(f"Blast date: {blast_date.date()}")
print()

results = []
all_stocks = df[df['date'] == signal_date]['stock'].unique()

for stock in all_stocks:
    prev_data     = df[(df['stock'] == stock) & (df['date'].isin(prev_dates))]
    prev_day_data = df[(df['stock'] == stock) & (df['date'] == prev_day)]
    signal_data   = df[(df['stock'] == stock) & (df['date'] == signal_date)]
    blast_data    = df[(df['stock'] == stock) & (df['date'] == blast_date)]

    if len(prev_data) < 2 or len(prev_day_data) == 0 or len(signal_data) == 0:
        continue

    price_range       = (prev_data['ltp'].max() - prev_data['ltp'].min()) / prev_data['ltp'].min() * 100
    avg_prev_vol_ratio = prev_data['vol_ratio'].mean()
    signal_vol_ratio  = signal_data['vol_ratio'].values[0]
    prev_close        = prev_day_data['ltp'].values[0]
    signal_close      = signal_data['ltp'].values[0]
    price_chg         = (signal_close - prev_close) / prev_close * 100

    blast_ratio = blast_data['vol_ratio'].values[0] if len(blast_data) > 0 else None

    # Apply pre-blast filter
    if (price_range < 4 and
        avg_prev_vol_ratio < 2 and
        signal_vol_ratio >= 1.5 and
        signal_vol_ratio <= 7):

        results.append({
            'stock': stock,
            'prev_3d_price_range': round(price_range, 2),
            'prev_3d_avg_vol': round(avg_prev_vol_ratio, 2),
            'signal_vol_ratio': round(signal_vol_ratio, 2),
            'signal_price_chg': round(price_chg, 2),
            'blast_ratio': round(blast_ratio, 2) if blast_ratio else None,
            'result': '🚀 BLAST' if blast_ratio and blast_ratio >= 8 else
                      '⚡ Moderate' if blast_ratio and blast_ratio >= 3 else '😴 Normal'
        })

res = pd.DataFrame(results).sort_values('blast_ratio', ascending=False)
blast    = (res['result'] == '🚀 BLAST').sum()
moderate = (res['result'] == '⚡ Moderate').sum()
normal   = (res['result'] == '😴 Normal').sum()

print(f"Total candidates on 29 June: {len(res)}")
print(f"🚀 BLAST next day:    {blast} ({blast/len(res)*100:.1f}%)")
print(f"⚡ Moderate next day: {moderate} ({moderate/len(res)*100:.1f}%)")
print(f"😴 Normal next day:   {normal} ({normal/len(res)*100:.1f}%)")
print()
print(res.to_string(index=False))
EOF
