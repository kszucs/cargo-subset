use crate::constants::PREFIX;

pub fn format_string(s: &str) -> String {
    format!("{}{}", PREFIX, s)
}

pub fn parse_number(s: &str) -> Result<i32, std::num::ParseIntError> {
    s.parse()
}
