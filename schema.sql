-- AI Online Voting System - MySQL Schema
-- Import this in phpMyAdmin / MySQL Workbench / mysql CLI

CREATE DATABASE IF NOT EXISTS ai_online_voting_system;
USE ai_online_voting_system;

-- ============================
-- USERS (admins + voters)
-- ============================
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,          -- hashed password, never plaintext
    cnic VARCHAR(20) DEFAULT NULL,
    phone VARCHAR(20) DEFAULT NULL,
    photo VARCHAR(255) DEFAULT NULL,
    role ENUM('admin','voter') NOT NULL DEFAULT 'voter',
    status ENUM('Pending','Approved','Rejected') NOT NULL DEFAULT 'Pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================
-- CANDIDATES
-- ============================
CREATE TABLE IF NOT EXISTS candidates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    party_name VARCHAR(150) NOT NULL,
    symbol VARCHAR(100) DEFAULT NULL,
    photo VARCHAR(255) DEFAULT NULL,
    manifesto TEXT,
    status ENUM('active','inactive') NOT NULL DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================
-- ELECTIONS
-- ============================
CREATE TABLE IF NOT EXISTS elections (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    start_date DATETIME NOT NULL,
    end_date DATETIME NOT NULL,
    status ENUM('upcoming','active','completed') NOT NULL DEFAULT 'upcoming',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================
-- VOTES
-- ============================
CREATE TABLE IF NOT EXISTS votes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    voter_id INT NOT NULL,
    candidate_id INT NOT NULL,
    election_id INT NOT NULL,
    voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_vote_per_election (voter_id, election_id),  -- DB-level guard: one vote per voter per election
    FOREIGN KEY (voter_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (candidate_id) REFERENCES candidates(id) ON DELETE CASCADE,
    FOREIGN KEY (election_id) REFERENCES elections(id) ON DELETE CASCADE
);

-- ============================
-- SEED: default admin account
-- Email: admin@voting.com | Password: Admin@123
-- (This hash was generated with werkzeug generate_password_hash)
-- Run create_admin.py included, OR use this pre-hashed value:
-- ============================
-- INSERT INTO users (full_name, email, password, role, status)
-- VALUES ('System Admin', 'admin@voting.com', '<paste generated hash here>', 'admin', 'Approved');
