-- Link Shortener Database Schema
-- Run this on your MySQL server

-- Create database
CREATE DATABASE IF NOT EXISTS link_shortener
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE link_shortener;
-- Create user (change password!)
-- CREATE USER IF NOT EXISTS 'linkshortener'@'localhost' IDENTIFIED BY 'your_secure_password_here';
-- GRANT ALL PRIVILEGES ON link_shortener.* TO 'linkshortener'@'localhost';
-- FLUSH PRIVILEGES;

-- Links table (new schema: suffix, destination, created_at, expires_at, ip_address)
CREATE TABLE IF NOT EXISTS links (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    suffix VARCHAR(64) NOT NULL UNIQUE,
    destination TEXT NOT NULL,
    -- created_at uses session time zone; app sets DB session to UTC
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    -- Store UTC datetimes (application normalizes to UTC)
    expires_at DATETIME NULL,
    ip_address VARCHAR(255) NULL,
    
    INDEX idx_expires_at (expires_at),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Clicks and blocked_domains tables removed per user request
