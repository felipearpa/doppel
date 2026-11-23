struct Left {
    func totals(orders: [Order]) -> [String: Int] {
        let paid = orders.filter { $0.status == "paid" }
        let grouped = Dictionary(grouping: paid) { $0.customer }
        return grouped.mapValues { entries in entries.reduce(0) { $0 + $1.amount } + 10 }
    }
}
