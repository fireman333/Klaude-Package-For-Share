// handoff preset — 黑白緊湊 (對應舊 handoff.css)
#set text(font: ("Helvetica Neue", "PingFang TC", "Apple Color Emoji"), lang: "zh", region: "tw", size: 10pt, fill: rgb("#222222"))
#set page(margin: (x: 14mm, y: 16mm))
#set par(justify: false, leading: 0.65em)

#set table(
  stroke: 0.5pt + rgb("#888888"),
  inset: (x: 8pt, y: 3pt),
  fill: (_, y) => if y == 0 { rgb("#eeeeee") } else { white },
)
#show table.cell: set align(left + top)
#show table.cell.where(y: 0): set text(weight: "bold")

#show heading.where(level: 1): it => block(width: 100%, above: 1.2em, below: 0.6em, breakable: false)[
  #set text(size: 16pt, fill: rgb("#000000"), weight: "bold")
  #it.body
  #v(0.08em)
  #line(length: 100%, stroke: 1pt + rgb("#333333"))
]
#show heading.where(level: 2): it => block(
  width: 100%, above: 1.1em, below: 0.5em, breakable: false,
  stroke: (bottom: 0.5pt + rgb("#999999")),
  inset: (bottom: 2pt),
)[
  #set text(size: 12.5pt, fill: rgb("#000000"), weight: "bold")
  #it.body
]
#show heading.where(level: 3): it => block(above: 0.8em, below: 0.35em)[
  #set text(size: 11pt, fill: rgb("#333333"), weight: "bold")
  #it.body
]
