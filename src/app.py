from fastapi import FastAPI, Depends, HTTPException, Body, Query, UploadFile
from pydantic import BaseModel
from backend.database import get_connection
from backend.auth import hash_password, verify_password, create_access_token
from backend.queries import CREATE_USER, CREATE_CONCERT, GET_USER_BY_USERNAME, GET_CONCERTS, ADD_TO_CART, GET_CART_ITEMS, DELETE_FROM_CART, GET_ORDERS
import psycopg2
from psycopg2.extras import DictCursor
import logging
from typing import List
from typing import Optional
from fastapi.responses import FileResponse
import os
from datetime import datetime

from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
app = FastAPI()


logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class NewConcertRequest(BaseModel):
    name: str
    description: str
    address: str
    price: float
    date: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    role: str = "user"

class LoginRequest(BaseModel):
    username: str
    password: str

class concertsItem(BaseModel):
    name: str
    description: str
    address: str
    price: float
    date: datetime
    image_url: str

class CartAddItem(BaseModel):
    username: str
    item_name: str
    quantity: int

class CartItem(BaseModel):
    item_name: str
    quantity: int
    price: float
    created_at: str

class ReviewRequest(BaseModel):
    username: str
    item_name: str
    rating: int
    review: str 

class Address(BaseModel):
    id: int
    user_id: int
    address: str
    name: str
    surname: str
    created_at: str

class Review(BaseModel):
    id: int
    user_id: int
    concerts_id: int
    rating: int
    review: str
    created_at: str

class User(BaseModel):
    id: int
    username: str
    role: str

class OrderRequest(BaseModel):
    username: str
    address: str
    name: str
    surname: str

class AddressRequest(BaseModel):
    username: str
    address: str
    name: str
    surname: str


@app.post("/admin/backup")
def create_backup():
    try:
        backup_file = "db_backup.sql"
        os.system(f"pg_dump -U ks -h localhost -p 8001 food > {backup_file}")
        
        return FileResponse(
            path=backup_file,
            filename=backup_file,
            media_type="application/sql"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при создании бэкапа: {str(e)}")

@app.post("/admin/restore")
async def restore_backup(file: UploadFile):
    try:
        backup_file = "/tmp/restore_backup.sql"
        with open(backup_file, "wb") as f:
            content = await file.read()
            f.write(content)

        os.system(f" psql -U myuser -h localhost -p 5432 postgres < backup_file")
        
        return {"status": "success", "message": "База данных успешно восстановлена из бэкапа"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при восстановлении базы данных: {str(e)}")

@app.post("/reviews/add")
async def add_review(review: ReviewRequest):
    conn = get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM users WHERE username = %s", (review.username,))
        user = cursor.fetchone()

        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        
        user_id = user['id']

        cursor.execute("SELECT id FROM concerts WHERE name = %s", (review.item_name,))
        item = cursor.fetchone()
        
        concerts_id = item['id']
        cursor.execute(
            """
            INSERT INTO reviews (user_id, concerts_id, rating, review)
            VALUES (%s, %s, %s, %s)
            """,
            (user_id, concerts_id, review.rating, review.review),
        )
        conn.commit()

        logging.info("Отзыв успешно добавлен в базу данных")
        return {"status": "success", "message": "Отзыв добавлен"}
    
    except Exception as e:
        conn.rollback()
        logging.error(f"Ошибка при добавлении отзыва: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка при добавлении отзыва: {str(e)}")
    finally:
        conn.close()
        logging.info("Соединение с базой данных закрыто")

@app.post("/address/save")
async def save_address(address_request: AddressRequest):
    conn = get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM users WHERE username = %s", (address_request.username,))
        user = cursor.fetchone()
        logging.info(user)
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        user_id = user['id']
        
        cursor.execute("SELECT id FROM user_info WHERE user_id = %s", (user_id,))
        address = cursor.fetchone()
        logging.info(address)

        if address:
            cursor.execute("""
                UPDATE user_info
                SET address = %s, name = %s, surname = %s, created_at = CURRENT_TIMESTAMP
                WHERE user_id = %s
            """, (address_request.address, address_request.name, address_request.surname, user_id))
        else:
            cursor.execute("""
                INSERT INTO user_info (user_id, address, name, surname, created_at)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            """, (user_id, address_request.address, address_request.name, address_request.surname))

        conn.commit()
        return {"status": "success", "message": "Адрес сохранён"}

    except Exception as e:
        conn.rollback()
        logging.error(f"Ошибка при сохранении адреса: {str(e)}")
        raise HTTPException(status_code=500, detail="Ошибка при сохранении адреса")
    
    finally:
        conn.close()


@app.get("/admin/payments")
def get_payments():
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute("""
                SELECT order_id, payment_method, amount, status, created_at
                FROM payments
                ORDER BY created_at DESC
                LIMIT 10
            """)
            payments = cursor.fetchall()
            return [dict(payment) for payment in payments]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при получении платежей: {str(e)}")
    finally:
        conn.close()

@app.get("/admin/reviews")
def get_all_reviews():
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute("""
                SELECT id, user_id, concerts_id, rating, review, created_at 
                FROM reviews 
                ORDER BY created_at DESC
                LIMIT 10
            """)
            reviews = cursor.fetchall()
            return [dict(review) for review in reviews]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при получении отзывов: {str(e)}")
    finally:
        conn.close()

@app.get("/admin/addresses")
def get_all_addresses():
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute("""
                SELECT id, user_id, address, name, surname, created_at 
                FROM user_info 
                ORDER BY created_at DESC
                LIMIT 10
            """)
            addresses = cursor.fetchall()
            return [dict(address) for address in addresses]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при получении адресов: {str(e)}")
    finally:
        conn.close()

@app.get("/")
def read_root():
    return {"message": "Hello World"}

@app.post("/register")
def register(request: RegisterRequest):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        hashed_password = hash_password(request.password)
        cursor.execute(CREATE_USER, (request.username, hashed_password, request.role))
        conn.commit()
        return {"status": "success", "message": "User registered successfully"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.post("/new_concert")
def add_new_concert(request: NewConcertRequest):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(CREATE_CONCERT, (request.name, request.description, request.address, request.price, request.date))
        conn.commit()
        return {"status": "success", "message": "Concert added successfully"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.post("/login")
def login(request: LoginRequest):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(GET_USER_BY_USERNAME, (request.username,))
        user = cursor.fetchone()
        if not user or not verify_password(request.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        token = create_access_token({"username": request.username, "role": user["role"]})
        return {"access_token": token, "role": user["role"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/concerts", response_model=list[concertsItem])
def get_concerts():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(GET_CONCERTS)
        concerts_items = cursor.fetchall()
        return concerts_items
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.post("/cart/add")
def add_to_cart(cart_item: CartAddItem):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(ADD_TO_CART, (cart_item.username, cart_item.item_name, cart_item.quantity))
        conn.commit()
        return {"status": "success", "message": "Item added to cart"}
    except Exception as e:
        conn.rollback()
        print(f"Ошибка добавления в корзину: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка добавления в корзину: {str(e)}")
    finally:
        conn.close()


from decimal import Decimal
from datetime import datetime

@app.get("/cart/{username}", response_model=list[CartItem])
def get_cart(username: str):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        print(f"Получение корзины для пользователя: {username}")
        cursor.execute(GET_CART_ITEMS, (username,))
        cart_items = cursor.fetchall()
        print(f"Полученные элементы корзины: {cart_items}")
        
        formatted_items = []
        for item in cart_items:
            formatted_items.append({
                "item_name": item["item_name"],
                "quantity": item["quantity"],
                "price": float(item["price"]),
                "created_at": item["created_at"].strftime("%d.%m.%Y %H:%M:%S") 
            })

        return formatted_items

    except Exception as e:
        print(f"Ошибка загрузки корзины: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки корзины: {str(e)}")
    finally:
        conn.close()

@app.delete("/cart/remove")
def remove_from_cart(username: str, item_name: str):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        print(f"Удаление из корзины: {username}, {item_name}") 
        cursor.execute(DELETE_FROM_CART, (username, item_name))
        removed_item = cursor.fetchone()
        conn.commit()

        if removed_item:
            return {"status": "success", "message": f"{item_name} удален из корзины"}
        else:
            raise HTTPException(status_code=404, detail="Элемент не найден в корзине")

    except Exception as e:
        conn.rollback()
        print(f"Ошибка удаления из корзины: {str(e)}") 
        raise HTTPException(status_code=500, detail=f"Ошибка удаления из корзины: {str(e)}")
    finally:
        conn.close()

@app.get("/concerts/search")
async def search_concerts(query: str = Query(..., description="Строка для поиска концертов")):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, name, description, address, date, price, available 
            FROM concerts 
            WHERE name ILIKE %s
        """, (f"%{query}%",))
        
        results = cursor.fetchall()
        return [
            {"id": row['id'], "name": row['name'], "description": row['description'], "address": row['address'], "date": row['date'], "price": row['price'], "available": row['available']}
            for row in results
        ]
    except Exception as e:
        logging.error(f"Ошибка при поиске концертов: {str(e)}")
        raise HTTPException(status_code=500, detail="Ошибка при поиске концертов")
    finally:
        conn.close()
class CheckoutResponse(BaseModel):
    status: str
    message: str

@app.post("/checkout/{username}", response_model=CheckoutResponse)
def checkout(username: str):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        print(f"Получен запрос на оформление заказа для пользователя: {username}")

        cursor.execute("SELECT id FROM users WHERE LOWER(username) = LOWER(%s)", (username,))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        user_id = user['id']


        cursor.execute("""
            SELECT concerts_id, quantity 
            FROM cart 
            WHERE user_id = %s
        """, (user_id,))
        cart_items = cursor.fetchall()

        if not cart_items:
            return {"status": "error", "message": "Корзина пуста"}

        print(f"Элементы корзины для пользователя {user_id}: {cart_items}")


        for item in cart_items:
            concerts_id, quantity = item['concerts_id'], item['quantity']
            if not isinstance(concerts_id, int) or not isinstance(quantity, int):
                raise HTTPException(status_code=500, detail="Неверные данные корзины")

            cursor.execute("""
                INSERT INTO orders (user_id, concerts_id, quantity, status)
                VALUES (%s, %s, %s, %s)
            """, (user_id, concerts_id, quantity, 'pending'))

        cursor.execute("DELETE FROM cart WHERE user_id = %s", (user_id,))
        conn.commit()

        return {"status": "success", "message": "Все элементы корзины оформлены в заказы"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при оформлении заказа: {str(e)}")
    finally:
        conn.close()
from fastapi import FastAPI, HTTPException

@app.get("/orders/{username}")
def get_orders(username: str):
    conn = get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        user_id = user["id"]

        cursor.execute("""
            SELECT 
                o.user_id AS user_id,
                SUM(m.price * o.quantity) AS total_price, -- Общая сумма неоплаченных товаров
                COUNT(o.id) AS order_count,              -- Количество неоплаченных заказов
                CASE 
                    WHEN COUNT(DISTINCT o.status) = 1 THEN MAX(o.status)
                    ELSE 'mixed'
                END AS overall_status
            FROM orders o
            JOIN concerts m ON o.concerts_id = m.id
            WHERE o.user_id = %s AND o.status = 'pending' -- Фильтруем только неоплаченные
            GROUP BY o.user_id;
        """, (user_id,))


        orders = cursor.fetchone()
        if not orders:
            return {"message": "У пользователя нет неоплаченных заказов"}

        result = {
            "user_id": orders["user_id"],
            "total_price": orders["total_price"],
            "order_count": orders["order_count"],
            "status": orders["overall_status"]
        }
        return result

    except Exception as e:
        print(f"Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка при получении заказов: {str(e)}")
    finally:
        conn.close()

@app.get("/orders1/{username}")
def get_all_orders(username: str):
    conn = get_connection()
    try:
        cursor = conn.cursor(cursor_factory=DictCursor)

        # Получение ID пользователя по имени
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        user_id = user["id"]

        # Получение всех заказов пользователя
        cursor.execute("""
            SELECT 
                o.user_id AS user_id,
                c.name AS concert_name,
                c.price AS concert_price,
                c.date AS date,
                o.quantity AS quantity,
                o.status AS status
            FROM orders o
            JOIN concerts c ON o.concerts_id = c.id
            WHERE o.user_id = %s;
        """, (user_id,))

        orders = cursor.fetchall()
        if not orders:
            return {"message": "У пользователя нет заказов"}

        # Форматирование данных
        formatted_orders = [
            {
                "user_id": order["user_id"],
                "concert_name": order["concert_name"],
                "concert_price": float(order["concert_price"]),
                "date": order["date"],
                "quantity": order["quantity"],
                "status": order["status"],
            }
            for order in orders
        ]
        return formatted_orders

    except Exception as e:
        logging.error(f"Ошибка при получении заказов: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка при получении заказов: {str(e)}")
    finally:
        conn.close()


@app.post("/pay_order/{user_id}")
def pay_order(
    user_id: int,
    payment_method: str = Body(..., example="credit_card"),
    amount: float = Body(..., example=100.50),
):
    conn = get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 
                SUM(m.price * o.quantity) AS total_price
            FROM orders o
            JOIN concerts m ON o.concerts_id = m.id
            WHERE o.user_id = %s AND o.status = 'pending'
        """, (user_id,))
        result = cursor.fetchone()
        total_price = result["total_price"] if result and result["total_price"] else 0

        if total_price == 0:
            raise HTTPException(status_code=404, detail="Нет товаров для оплаты")
        if amount < total_price:
            raise HTTPException(status_code=400, detail=f"Сумма оплаты ({amount}) недостаточна, требуется {total_price}")

        cursor.execute("""
            UPDATE orders
            SET status = 'paid'
            WHERE user_id = %s AND status = 'pending'
        """, (user_id,))

        cursor.execute("""
            INSERT INTO payments (order_id, payment_method, amount, status)
            VALUES (%s, %s, %s, %s)
        """, (1, payment_method, amount, "completed"))
        conn.commit()
        return {"status": "success", "message": f"Заказ успешно оплачен"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при оплате заказов: {str(e)}")
    finally:
        conn.close()

