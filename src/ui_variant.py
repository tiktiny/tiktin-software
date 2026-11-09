# איזה ממשק מותקן: A = הממשק הקיים, B = הממשק החדש ("קו אדום").
# קובץ ההתקנה של גרסה B מוסיף ליד הקוד את הקובץ new_ui.flag.
import os

NEW_UI = os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "new_ui.flag"))
VARIANT = "B" if NEW_UI else "A"
