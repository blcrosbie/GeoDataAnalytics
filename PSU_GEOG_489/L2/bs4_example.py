import requests

from bs4 import BeautifulSoup

url = "https://www.e-education.psu.edu/geog489/l1.html"
response = requests.get(url) 
soup = BeautifulSoup(response.text, 'html.parser') 
 
print(soup.find('title'))