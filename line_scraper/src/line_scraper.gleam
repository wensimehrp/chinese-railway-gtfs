import gleam/dict
import gleam/erlang/process
import gleam/http/request
import gleam/httpc
import gleam/io
import gleam/json
import gleam/list
import gleam/result
import gleam/string
import gleam/uri
import presentable_soup as soup

pub fn main() -> Nil {
  let assert Ok(line_list) = query_index()
  let json_string =
    list.map(line_list, fn(line_name) {
      let subject = process.new_subject()
      io.println_error("Started querying line " <> line_name)
      process.sleep(200)
      process.spawn(fn() {
        let grid = query_line(line_name)
        io.println_error(
          "Queried "
          <> line_name
          <> ". Result:"
          <> case grid |> result.is_ok {
            True -> "Sucess"
            False -> "Failed"
          },
        )
        process.send(subject, grid)
      })
      #(line_name, subject)
    })
    |> list.filter_map(fn(item) {
      let #(line_name, subject) = item
      process.receive(subject, 10_000)
      |> result.map(fn(data) {
        io.println_error("Received data for line " <> line_name)
        #(line_name, data)
      })
      |> result.map_error(fn(err) {
        io.println_error("Failed to receive data for line " <> line_name)
        err
      })
    })
    |> list.filter_map(fn(item) {
      let #(line_name, grid) = item
      grid
      |> result.map(fn(data) {
        io.println_error("Parsed data for line " <> line_name)
        #(line_name, data)
      })
      |> result.map_error(fn(err) {
        io.println_error(
          "Failed to parse HTML for line " <> line_name <> ": " <> err,
        )
        err
      })
    })
    |> list.sort(by: fn(a, b) {
      let #(a, _) = a
      let #(b, _) = b
      string.compare(a, b)
    })
    |> dict.from_list
    |> fn(this) { this }
    |> json.dict(fn(k) { k }, fn(grid) {
      json.array(from: grid, of: fn(row) {
        json.array(from: row, of: json.string)
      })
    })
  io.print(json_string |> json.to_string)
  Nil
}

fn query_index() -> Result(List(String), String) {
  let index_url = "https://jprailfan.com/tools/stat/"
  let assert Ok(req) = request.to(index_url)
  use resp <- result.try(
    httpc.send(req)
    |> result.map_error(fn(err) {
      "Failed to invoke web request: " <> err |> string.inspect
    }),
  )
  soup.element([soup.with_tag("datalist"), soup.with_id("line")])
  |> soup.descendants([soup.with_tag("option")])
  |> soup.return(soup.text_content())
  |> soup.scrape(resp.body)
  |> result.map(fn(scraped) { scraped |> list.flatten })
  |> result.map_error(fn(err) {
    "Failed to query html: " <> err |> string.inspect
  })
}

fn query_line(line_name: String) -> Result(List(List(String)), String) {
  let query_url =
    "https://jprailfan.com/tools/stat/?linename="
    <> uri.percent_encode(line_name)
  let assert Ok(req) = request.to(query_url)
  use resp <- result.try(
    httpc.send(req)
    |> result.map_error(fn(err) {
      "Failed to invoke web request: " <> err |> string.inspect
    }),
  )
  soup.element([soup.with_tag("table"), soup.with_attribute("width", "70%")])
  |> soup.descendant([soup.with_tag("tbody")])
  |> soup.descendants([soup.with_tag("tr")])
  |> soup.descendants([soup.with_tag("td")])
  |> soup.return(soup.text_content())
  |> soup.scrape(resp.body)
  |> result.map(fn(scraped) {
    let #(_, data) = scraped |> list.map(list.flatten) |> list.split(2)
    data
  })
  |> result.map_error(fn(err) {
    "Failed to query html: " <> err |> string.inspect
  })
}
