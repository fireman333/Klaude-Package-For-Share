// report preset — navy 學術風 (對應舊 report.css)
#set text(font: ("Helvetica Neue", "PingFang TC", "Apple Color Emoji"), lang: "zh", region: "tw", size: 10.5pt, fill: rgb("#1a1a1a"))
#set page(margin: (x: 16mm, y: 18mm))
#set par(justify: false, leading: 0.7em)

#set table(
  stroke: 0.5pt + rgb("#9bb3cc"),
  inset: (x: 8pt, y: 5pt),
  fill: (_, y) => if y == 0 { rgb("#e8eef5") } else if calc.odd(y) { rgb("#f7f9fc") } else { white },
)
#show table.cell: set align(left + top)
#show table.cell.where(y: 0): set text(weight: "bold")

#show heading.where(level: 1): it => block(width: 100%, above: 1.4em, below: 0.8em, breakable: false)[
  #set text(size: 19pt, fill: rgb("#1f4e79"), weight: "bold")
  #it.body
  #v(0.1em)
  #line(length: 100%, stroke: 2pt + rgb("#1f4e79"))
]
#show heading.where(level: 2): it => block(
  width: 100%, above: 1.25em, below: 0.6em, breakable: false,
  inset: (left: 8pt, top: 2pt, bottom: 2pt),
  stroke: (left: 4pt + rgb("#1f4e79")),
)[
  #set text(size: 14pt, fill: rgb("#1f4e79"), weight: "bold")
  #it.body
]
#show heading.where(level: 3): it => block(above: 0.9em, below: 0.4em)[
  #set text(size: 12pt, fill: rgb("#2e2e2e"), weight: "bold")
  #it.body
]
