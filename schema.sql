-- =====================================================================
-- Customer Loyalty & Rewards Program - Database Schema
-- Engine: MySQL 8.0+
-- =====================================================================

DROP DATABASE IF EXISTS loyalty_program;
CREATE DATABASE loyalty_program CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE loyalty_program;

-- ---------------------------------------------------------------------
-- 1. TIERS  -- defines membership tiers and their point multipliers
-- ---------------------------------------------------------------------
CREATE TABLE reward_tiers (
    tier_id            INT AUTO_INCREMENT PRIMARY KEY,
    tier_name          VARCHAR(20)  NOT NULL UNIQUE,
    min_lifetime_points INT         NOT NULL DEFAULT 0,
    points_multiplier  DECIMAL(3,2) NOT NULL DEFAULT 1.00,
    CHECK (points_multiplier > 0)
) ENGINE=InnoDB;

INSERT INTO reward_tiers (tier_name, min_lifetime_points, points_multiplier) VALUES
    ('Bronze',    0, 1.00),
    ('Silver',  500, 1.25),
    ('Gold',   1500, 1.50),
    ('Platinum', 3000, 2.00);

-- ---------------------------------------------------------------------
-- 2. CUSTOMERS
-- ---------------------------------------------------------------------
CREATE TABLE customers (
    customer_id      INT AUTO_INCREMENT PRIMARY KEY,
    first_name       VARCHAR(50)  NOT NULL,
    last_name        VARCHAR(50)  NOT NULL,
    email            VARCHAR(100) NOT NULL UNIQUE,
    phone            VARCHAR(20),
    address          VARCHAR(255),
    registration_date DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lifetime_points  INT          NOT NULL DEFAULT 0,   -- total points ever earned
    membership_tier  VARCHAR(20)  NOT NULL DEFAULT 'Bronze',
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    FOREIGN KEY (membership_tier) REFERENCES reward_tiers(tier_name)
) ENGINE=InnoDB;

CREATE INDEX idx_customers_email ON customers(email);

-- ---------------------------------------------------------------------
-- 3. PRODUCTS  -- catalog of items customers can purchase
-- ---------------------------------------------------------------------
CREATE TABLE products (
    product_id     INT AUTO_INCREMENT PRIMARY KEY,
    product_name   VARCHAR(150) NOT NULL,
    price          DECIMAL(10,2) NOT NULL CHECK (price >= 0),
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 4. PURCHASES
-- ---------------------------------------------------------------------
CREATE TABLE purchases (
    purchase_id      INT AUTO_INCREMENT PRIMARY KEY,
    customer_id      INT NOT NULL,
    product_id       INT NULL,
    quantity         INT NOT NULL DEFAULT 1,
    purchase_amount  DECIMAL(10,2) NOT NULL CHECK (purchase_amount >= 0),
    purchase_date    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    store_location   VARCHAR(100),
    points_earned    INT NOT NULL DEFAULT 0,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(product_id)
) ENGINE=InnoDB;

CREATE INDEX idx_purchases_customer ON purchases(customer_id);
CREATE INDEX idx_purchases_date ON purchases(purchase_date);

-- Sample products so the dashboard isn't empty on first run (optional)
INSERT INTO products (product_name, price) VALUES
    ('Wireless Headphone', 1500.00),
    ('Smart Watch', 2500.00),
    ('Bluetooth Speaker', 1200.00),
    ('Power Bank', 800.00),
    ('Laptop Bag', 700.00);

-- ---------------------------------------------------------------------
-- 5. POINTS LEDGER
--    Every points event (earn / redeem / expire / adjust) is logged here.
--    EARN rows carry an expiry_date and remaining_points (for FIFO
--    consumption during redemption and expiration).
-- ---------------------------------------------------------------------
CREATE TABLE points_ledger (
    ledger_id         INT AUTO_INCREMENT PRIMARY KEY,
    customer_id       INT NOT NULL,
    points            INT NOT NULL,               -- positive=earn, negative=redeem/expire
    transaction_type  ENUM('EARN','REDEEM','EXPIRE','ADJUST') NOT NULL,
    reference_type    VARCHAR(20),                 -- PURCHASE / REDEMPTION / SYSTEM
    reference_id      INT,                         -- purchase_id or redemption_id
    earned_date       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expiry_date       DATETIME NULL,               -- only set on EARN rows
    remaining_points  INT NOT NULL DEFAULT 0,      -- unredeemed balance of an EARN row
    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE INDEX idx_ledger_customer ON points_ledger(customer_id);
CREATE INDEX idx_ledger_type ON points_ledger(transaction_type);
CREATE INDEX idx_ledger_expiry ON points_ledger(expiry_date);

-- ---------------------------------------------------------------------
-- 6. REWARDS CATALOG
-- ---------------------------------------------------------------------
CREATE TABLE rewards_catalog (
    reward_id        INT AUTO_INCREMENT PRIMARY KEY,
    reward_name       VARCHAR(100) NOT NULL,
    description       VARCHAR(255),
    points_required   INT NOT NULL CHECK (points_required > 0),
    is_active         BOOLEAN NOT NULL DEFAULT TRUE
) ENGINE=InnoDB;

INSERT INTO rewards_catalog (reward_name, description, points_required) VALUES
    ('₹5 Store Credit',   'Redeem for ₹5 off your next purchase', 50),
    ('₹10 Store Credit',  'Redeem for ₹10 off your next purchase', 100),
    ('Free Shipping',     'One free shipping voucher', 25),
    ('₹25 Gift Card',     'Redeem for a ₹25 gift card', 250);

-- ---------------------------------------------------------------------
-- 7. REDEMPTIONS
--    reward_id is nullable to support freeform "redeem N points" from
--    the dashboard, in addition to fixed catalog redemptions.
-- ---------------------------------------------------------------------
CREATE TABLE redemptions (
    redemption_id     INT AUTO_INCREMENT PRIMARY KEY,
    customer_id       INT NOT NULL,
    reward_id         INT NULL,
    points_redeemed   INT NOT NULL,
    reward_value      DECIMAL(10,2) NULL,
    redemption_date   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status            ENUM('COMPLETED','CANCELLED') NOT NULL DEFAULT 'COMPLETED',
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE,
    FOREIGN KEY (reward_id) REFERENCES rewards_catalog(reward_id)
) ENGINE=InnoDB;

CREATE INDEX idx_redemptions_customer ON redemptions(customer_id);

-- ---------------------------------------------------------------------
-- 8. VIEW: current available (non-expired, unredeemed) point balance
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW customer_points_balance AS
SELECT
    c.customer_id,
    CONCAT(c.first_name, ' ', c.last_name) AS customer_name,
    c.membership_tier,
    c.lifetime_points,
    COALESCE(SUM(CASE WHEN pl.transaction_type = 'EARN'
                       AND (pl.expiry_date IS NULL OR pl.expiry_date > NOW())
                  THEN pl.remaining_points ELSE 0 END), 0) AS available_points
FROM customers c
LEFT JOIN points_ledger pl ON pl.customer_id = c.customer_id
GROUP BY c.customer_id, c.first_name, c.last_name, c.membership_tier, c.lifetime_points;

-- ---------------------------------------------------------------------
-- 9. STORED PROCEDURE: expire points whose expiry_date has passed
--    Call periodically (daily) via cron, app scheduler, or the EVENT below.
-- ---------------------------------------------------------------------
DELIMITER $$

CREATE PROCEDURE expire_old_points()
BEGIN
    DECLARE done INT DEFAULT FALSE;
    DECLARE v_ledger_id INT;
    DECLARE v_customer_id INT;
    DECLARE v_remaining INT;

    DECLARE cur CURSOR FOR
        SELECT ledger_id, customer_id, remaining_points
        FROM points_ledger
        WHERE transaction_type = 'EARN'
          AND remaining_points > 0
          AND expiry_date IS NOT NULL
          AND expiry_date <= NOW();
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = TRUE;

    OPEN cur;
    read_loop: LOOP
        FETCH cur INTO v_ledger_id, v_customer_id, v_remaining;
        IF done THEN
            LEAVE read_loop;
        END IF;

        INSERT INTO points_ledger
            (customer_id, points, transaction_type, reference_type, reference_id, remaining_points)
        VALUES
            (v_customer_id, -v_remaining, 'EXPIRE', 'SYSTEM', v_ledger_id, 0);

        UPDATE points_ledger
        SET remaining_points = 0
        WHERE ledger_id = v_ledger_id;
    END LOOP;
    CLOSE cur;
END$$

DELIMITER ;

-- Optional: automatic daily expiration (requires: SET GLOBAL event_scheduler = ON;)
CREATE EVENT IF NOT EXISTS ev_expire_points
ON SCHEDULE EVERY 1 DAY
DO CALL expire_old_points();
