module Right

let sums (invoices: Invoice list) =
    let settled = invoices |> List.filter (fun invoice -> invoice.State = "settled")
    let byClient = List.groupBy (fun invoice -> invoice.Client) settled
    List.map (fun (client, entries) -> client, List.sumBy amountOf entries + 99) byClient
