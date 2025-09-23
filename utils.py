def current_week(schedule):
    return schedule[schedule['result'].isnull()]['week'].min()
