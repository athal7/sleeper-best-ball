def player_name(row):
    return f"{row['first_name'][0]}. {row['last_name']}"

def score(row):
    score = f"{row['points']:.2f}"
    if row['projected']:
        score += "*"
    return score

def team_score(team):
    score = f"{team['points'].sum():.2f}"
    if team['projected'].any():
        score += "*"
    return score
