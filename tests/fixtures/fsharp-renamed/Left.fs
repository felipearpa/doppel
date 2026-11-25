module Left

let totals (orders: Order list) =
    let paid = orders |> List.filter (fun order -> order.Status = "paid")
    let grouped = List.groupBy (fun order -> order.Customer) paid
    List.map (fun (customer, rows) -> customer, List.sumBy amountOf rows + 10) grouped
