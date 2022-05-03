from woocommerce import API
from os import getenv
import json

import logging

# Get an instance of a logger
LOGGER = logging.getLogger(__name__)

# Retrieve the environmental variables required
marketplace_url = getenv("MARKETPLACE_URL", "")
market_consumer_key = getenv("M_CONSUMER_KEY", "")
market_consumer_secret = getenv("M_CONSUMER_SECRET", "")


def check_orders_for_user(user_name):
    # Create the WooCommerce client
    wc_api = API(url=marketplace_url, consumer_key=market_consumer_key, consumer_secret=market_consumer_secret,
                 version="wc/v3")

    LOGGER.info("Connecting with the WooCommerce...")
    # The API fails to list all customers, so we start iterating through all the orders
    ordered_apps_list = []
    response_orders = wc_api.get("orders")
    orders_list = response_orders.json()
    LOGGER.info("WooCommerce response orders: " + str(orders_list))
    for order_info in orders_list:
        # Detect if the order was made by our user
        order_customer = order_info["customer_id"]
        response_user = wc_api.get("customers/"+str(order_customer))
        user_info = response_user.json()
        # LOGGER.info("WooCommerce response customers: " + str(user_info))
        # If the order was made by our user, add to the list of allowed applications (extract blueprint name)
        if user_info["username"] == user_name:
            items_list = order_info["line_items"]
            for item_info in items_list:
                item_id = item_info["product_id"]
                item_response = wc_api.get("products/" + str(item_id))
                item_full_info = item_response.json()
                item_name = item_full_info["name"]
                LOGGER.info("User has access to item: " + item_name)
                blueprint_name = item_full_info["attributes"][0]["options"][0]
                LOGGER.info("Item blueprint info: " + blueprint_name)
                ordered_apps_list.append(blueprint_name)

    return ordered_apps_list
