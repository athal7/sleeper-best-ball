def current_week(schedule):
    return schedule[schedule['result'].isnull()]['week'].min()


def is_game_over(schedule, week, team):
    team_game = schedule[((schedule['home_team'] == team) | (
        schedule['away_team'] == team)) & (schedule['week'] == week)]
    team_result = team_game['result'] if not team_game.empty else None
    return team_result.notnull().all() if team_result is not None else False
