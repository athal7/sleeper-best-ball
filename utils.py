import pandas as pd


def current_week(schedule):
    return schedule[schedule['result'].isnull()]['week'].min()


def is_game_over(schedule, week, team):
    if team == 'LAR':
        team = 'LA'
    team_game = schedule[((schedule['home_team'] == team) | (
        schedule['away_team'] == team)) & (schedule['week'] == week)]
    team_result = team_game['result'] if not team_game.empty else None
    return team_result.notnull().all() if team_result is not None else False


def calculate_optimistic_starters(df):
    # Only consider players who played or have a projection
    df = df.copy()
    df['optimistic'] = df.apply(get_optimistic_score, axis=1)
    df = df[df['optimistic'].notnull()]
    # Split by position
    qbs = df[df['position'] == 'QB'].sort_values(
        'optimistic', ascending=False)
    rbs = df[df['position'] == 'RB'].sort_values(
        'optimistic', ascending=False)
    wrs = df[df['position'] == 'WR'].sort_values(
        'optimistic', ascending=False)
    tes = df[df['position'] == 'TE'].sort_values(
        'optimistic', ascending=False)
    flex = df[df['position'].isin(['RB', 'WR', 'TE'])].sort_values(
        'optimistic', ascending=False)
    superflex = df.sort_values('optimistic', ascending=False)

    starters = []
    # 1 QB
    qb_starters = qbs.head(1).to_dict('records')
    starters += qb_starters
    # 3 RB
    rb_starters = rbs.head(3).to_dict('records')
    for i, p in enumerate(rb_starters, 1):
        p['position'] = f'RB{i}'
    starters += rb_starters
    # 3 WR
    wr_starters = wrs.head(3).to_dict('records')
    for i, p in enumerate(wr_starters, 1):
        p['position'] = f'WR{i}'
    starters += wr_starters
    # 2 TE
    te_starters = tes.head(2).to_dict('records')
    for i, p in enumerate(te_starters, 1):
        p['position'] = f'TE{i}'
    starters += te_starters
    # 1 RB/WR/TE FLEX (not already counted)
    used_ids = {p['player_id'] for p in starters}
    flex_avail = flex[~flex['player_id'].isin(used_ids)]
    flex_starters = flex_avail.head(1).to_dict('records')
    for i, p in enumerate(flex_starters, 1):
        p['position'] = f'FLEX'
    starters += flex_starters
    used_ids = {p['player_id'] for p in starters}
    # 1 SUPERFLEX (QB/RB/WR/TE, not already counted)
    superflex_avail = superflex[~superflex['player_id'].isin(used_ids)]
    superflex_starters = superflex_avail.head(1).to_dict('records')
    for i, p in enumerate(superflex_starters, 1):
        p['position'] = f'SFLEX'
    starters += superflex_starters
    # Calculate total
    total = sum(p['optimistic']
                for p in starters if p['optimistic'] is not None)
    return total, starters


def get_optimistic_score(player):
    if player['game_played']:
        return player['points']
    return max(player['projection'], player['points'])


def format_score(x):
    return f"{x:.2f}".rstrip('0').rstrip('.') if isinstance(x, float) else x
