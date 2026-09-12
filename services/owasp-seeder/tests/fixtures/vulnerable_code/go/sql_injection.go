package main

import (
	"database/sql"
	"fmt"
)

func GetUserByID(db *sql.DB, userID string) (*User, error) {
	// 🔴 VULNERABLE SITE: Sprintf форматирование в SQL query
	query := fmt.Sprintf("SELECT * FROM users WHERE id = %s", userID)

	rows, err := db.Query(query)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var user User
	if rows.Next() {
		return &user, rows.Scan(&user.ID, &user.Name)
	}

	return nil, fmt.Errorf("user not found")
}

func GetUserByUsername(db *sql.DB, username string) (*User, error) {
	// 🔴 VULNERABLE SITE: String formatting в SQL query с одинарными кавычками
	query := fmt.Sprintf("SELECT * FROM users WHERE username = '%s'", username)

	rows, err := db.Query(query)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var user User
	if rows.Next() {
		return &user, rows.Scan(&user.ID, &user.Name)
	}

	return nil, fmt.Errorf("user not found")
}

// User представляет модель пользователя
type User struct {
	ID   int
	Name string
}
