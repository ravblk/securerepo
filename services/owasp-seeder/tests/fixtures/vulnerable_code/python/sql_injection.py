

def get_user_by_id(user_id):

    import sqlite3

    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE id = {user_id}"
    result = cursor.execute(query)


    return result.fetchall()

def get_user_by_username(username):
   
    import sqlite3

    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()

    query = "SELECT * FROM users WHERE username = '{}'".format(username)
    result = cursor.execute(query)

    # Безопасная альтернатива:
    # query = "SELECT * FROM users WHERE username = ?"
    # result = cursor.execute(query, (username,))

    return result.fetchall()