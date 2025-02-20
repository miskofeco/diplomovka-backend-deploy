from newspaper import Article

url = "https://www.aktuality.sk/clanok/vqQHmW2/tri-odkazy-ktore-by-mal-od-koalicnych-politikov-pocut-generalny-tajomnik-nato-nazor-tomasa-valaska-a-ivana-korcoka/"  # Example URL
article = Article(url)

article.download()
article.parse()

headline = article.title
author = article.authors  # sometimes returns a list
publish_date = article.publish_date
text = article.text

print("Headline:", headline)
print("Author(s):", author)
print("Publish Date:", publish_date)
print("Article Text:", text)