import re

# Define input and output file names
input_file = "input.txt"
output_file = "result.txt"

# Open input file for reading
with open(input_file, "r", encoding="utf-8") as file:
    # Read input file content
    input_text = file.read()

# Remove rows that contain "Расписание Богослужений" or "Прихода"
input_text = re.sub(r'Расписание Богослужений.*?\n|Прихода.*?\n', '', input_text)

# Remove "(" and ")" in rows that contain the day of the week
input_text = re.sub(r'(\b[а-я]+)\s*\(\s*([а-я]+)\s*\)', r'\1, \2', input_text, flags=re.IGNORECASE)

# Replace time format from "hh-mm" to "hh:mm"
input_text = re.sub(r'(\d{1,2})-(\d{2})(?!\d)', r'\1:\2 -', input_text)

# Replace time format from "h:mm" to "hh:mm"
input_text = re.sub(r'(?<!\d)(\d):(\d{2})(?!\d)', r'0\1:\2', input_text)

# Remove empty rows and more than one spaces
input_text = re.sub(r'\n\s*\n', '\n', input_text)
input_text = re.sub(r'[ ]{2,}', ' ', input_text)

# Split input text into rows
rows = input_text.strip().split("\n")

# Define output text variable
output_text = ""

# Loop through rows
for row in rows:
    # Check if row contains month and day name
    if re.search(r'\b(?:Январ[ья]|Феврал[ья]|Марта?|Апрел[ья]|Ма[йя]|Июн[ья]|Июл[ья]|Августа?|Сентябр[ья]|Октябр[ья]|Ноябр[ья]|Декабр[ья])\s*,\s*(?:Понедельник|Вторник|Сред[ау]|Четверг|Пятниц[ау]|Суббот[ау]|Воскресенье)\s*', row, flags=re.IGNORECASE):
        # Add row with <h3> tag to output text
        output_text += f"<h3>{row}</h3>\n"
    else:
        # Add row with <br> tag to output text
        output_text += f"<br />{row.strip()}\n"

# Remove spaces after <br> and <h3> tag
output_text = re.sub(r'<br />\s*', '<br />', output_text)
output_text = re.sub(r'<h3>\s*', '<h3>', output_text)

# Open output file for writing
with open(output_file, "w", encoding="utf-8") as file:
    # Write output text to output file
    file.write(output_text)
    
print("Done.")
