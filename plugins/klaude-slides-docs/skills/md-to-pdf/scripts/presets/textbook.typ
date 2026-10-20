// textbook preset — 大字米色講義風 (對應舊 textbook.css)
#set text(font: ("Helvetica Neue", "PingFang TC", "Apple Color Emoji"), lang: "zh", region: "tw", size: 12pt, fill: rgb("#1a1a1a"))
#set page(margin: (x: 20mm, y: 22mm), fill: rgb("#fffdf6"))
#set par(justify: false, leading: 0.85em)

#set table(
  stroke: 0.5pt + rgb("#cda06a"),
  inset: 7pt,
  fill: (_, y) => if y == 0 { rgb("#fdf3df") } else if calc.odd(y) { rgb("#fffaf0") } else { white },
)
#show table.cell: set align(left + top)
#show table.cell.where(y: 0): set text(weight: "bold", fill: rgb("#6b3410"))

#show heading.where(level: 1): it => block(width: 100%, above: 1.5em, below: 0.95em, breakable: false)[
  #set text(size: 21pt, fill: rgb("#6b3410"), weight: "bold")
  #it.body
  #v(0.12em)
  #line(length: 100%, stroke: 1pt + rgb("#b87333"))
  #v(1.6pt)
  #line(length: 100%, stroke: 1pt + rgb("#b87333"))
]
#show heading.where(level: 2): it => block(
  width: 100%, above: 1.3em, below: 0.7em, breakable: false,
  fill: rgb("#fdf3df"),
  inset: (left: 11pt, top: 6pt, bottom: 6pt, right: 8pt),
  stroke: (left: 5pt + rgb("#b87333")),
)[
  #set text(size: 15pt, fill: rgb("#6b3410"), weight: "bold")
  #it.body
]
#show heading.where(level: 3): it => block(above: 1.0em, below: 0.45em)[
  #set text(size: 12.5pt, fill: rgb("#555555"), weight: "bold")
  #it.body
]
