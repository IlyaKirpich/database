
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO users (username, password_hash, role) 
VALUES
    ('admin', '123', 'admin'),
    ('user1', '456', 'user'),
    ('user2', '789', 'user')
ON CONFLICT (username) DO NOTHING; -- Пропускает вставку, если пользователь уже существует

-- Создание таблицы концертов
CREATE TABLE IF NOT EXISTS concerts (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL, -- Уникальное ограничение
    description TEXT,
    address TEXT,
    price NUMERIC(10, 2) NOT NULL,
    date TIMESTAMP,
    available BOOLEAN DEFAULT TRUE
);

-- Добавление концертов
INSERT INTO concerts (name, description, address, price, date, available) 
VALUES
    ('Imagine dragons', 'An alternative rock and pop band known for their anthemic, energetic songs blending rock, electronic, and pop elements', 'Grimau st. 76', 8.99, '2024-12-25 19:00:00', TRUE),
    ('Rammstein', 'Just a crazy rock concert', 'Red square', 99.49, '2024-12-25 19:00:00', TRUE),
    ('Twenty one pilots', 'An alternative pop and indie duo combining elements of pop, rock, hip-hop, and electronic music with introspective and emotional lyrics', 'Streshka', 7.99, '2024-12-25 19:00:00', TRUE),
    ('Ed Sheeran', 'Kvartirnik with unbelievable songs', 'Bashnya room 405/2', 4.49, '2024-12-25 19:00:00', TRUE)
ON CONFLICT (name) DO NOTHING; -- Пропускает вставку, если товар уже существует

-- Создание таблицы заказов
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE, -- Автоудаление связанных заказов при удалении пользователя
    concerts_id INT NOT NULL REFERENCES concerts(id) ON DELETE CASCADE, -- Автоудаление заказов при удалении товара
    quantity INT NOT NULL CHECK (quantity > 0), -- Ограничение: количество должно быть положительным
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы корзины
CREATE TABLE IF NOT EXISTS cart (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE, -- Автоудаление элементов корзины при удалении пользователя
    concerts_id INT NOT NULL REFERENCES concerts(id) ON DELETE CASCADE, -- Автоудаление элементов корзины при удалении товара
    quantity INT NOT NULL CHECK (quantity > 0), -- Ограничение: количество должно быть положительным
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Логи событий
CREATE TABLE IF NOT EXISTS event_logs (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50),
    event_description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы адресов эл. почты
CREATE TABLE IF NOT EXISTS user_info (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE, 
    address VARCHAR(255) NOT NULL,
    name VARCHAR(100),
    surname VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы платежей
CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    order_id INT NOT NULL REFERENCES orders(id) ON DELETE CASCADE, -- Удаление платежа при удалении заказа
    payment_method VARCHAR(50),
    amount NUMERIC(10, 2) NOT NULL CHECK (amount >= 0), -- Сумма платежа не может быть отрицательной
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы отзывов
CREATE TABLE IF NOT EXISTS reviews (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE, -- Удаление отзывов при удалении пользователя
    concerts_id INT NOT NULL REFERENCES concerts(id) ON DELETE CASCADE, -- Удаление отзывов при удалении товара
    rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5), -- Ограничение: рейтинг от 1 до 5
    review TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE OR REPLACE PROCEDURE process_payment(user_id INT, payment_method VARCHAR, amount NUMERIC)
LANGUAGE plpgsql AS $$
DECLARE
    total_amount NUMERIC;
    order_ids INT[];
BEGIN
    -- Рассчитываем общую сумму заказов пользователя
    total_amount := calculate_total_amount(user_id);

    -- Проверяем, достаточно ли суммы для оплаты
    IF amount < total_amount THEN
        RAISE EXCEPTION 'Недостаточная сумма для оплаты. Требуется %', total_amount;
    END IF;

    -- Обновляем статус заказов
    UPDATE orders
    SET status = 'paid'
    WHERE user_id = user_id AND status = 'pending';

    -- Добавляем запись в таблицу payments
    INSERT INTO payments (user_id, payment_method, amount, status)
    VALUES (user_id, payment_method, amount, 'completed');
END;
$$;
CREATE OR REPLACE FUNCTION log_event()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO event_logs (event_type, event_description, created_at)
    VALUES (
        TG_OP, -- Тип операции: INSERT, UPDATE, DELETE
        FORMAT(
            'Table: %s, Old: %s, New: %s',
            TG_TABLE_NAME, -- Имя таблицы
            ROW(OLD.*)::TEXT, -- Старые данные (для DELETE и UPDATE)
            ROW(NEW.*)::TEXT  -- Новые данные (для INSERT и UPDATE)
        ),
        CURRENT_TIMESTAMP
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггеры для таблицы users
CREATE TRIGGER log_users_event
AFTER INSERT OR UPDATE OR DELETE ON users
FOR EACH ROW EXECUTE FUNCTION log_event();

-- Триггеры для таблицы concerts
CREATE TRIGGER log_concerts_event
AFTER INSERT OR UPDATE OR DELETE ON concerts
FOR EACH ROW EXECUTE FUNCTION log_event();

-- Триггеры для таблицы orders
CREATE TRIGGER log_orders_event
AFTER INSERT OR UPDATE OR DELETE ON orders
FOR EACH ROW EXECUTE FUNCTION log_event();

-- Триггеры для таблицы cart
CREATE TRIGGER log_cart_event
AFTER INSERT OR UPDATE OR DELETE ON cart
FOR EACH ROW EXECUTE FUNCTION log_event();

-- Триггеры для таблицы delivery_addresses
CREATE TRIGGER log_user_info_event
AFTER INSERT OR UPDATE OR DELETE ON user_info
FOR EACH ROW EXECUTE FUNCTION log_event();

-- Триггеры для таблицы payments
CREATE TRIGGER log_payments_event
AFTER INSERT OR UPDATE OR DELETE ON payments
FOR EACH ROW EXECUTE FUNCTION log_event();

-- Триггеры для таблицы reviews
CREATE TRIGGER log_reviews_event
AFTER INSERT OR UPDATE OR DELETE ON reviews
FOR EACH ROW EXECUTE FUNCTION log_event();


CREATE OR REPLACE VIEW unpaid_orders_summary AS
SELECT 
    o.user_id AS user_id,
    SUM(m.price * o.quantity) AS total_price,
    COUNT(o.id) AS order_count
FROM orders o
JOIN concerts m ON o.concerts_id = m.id
WHERE o.status = 'pending'
GROUP BY o.user_id;
