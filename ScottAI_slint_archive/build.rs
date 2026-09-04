fn main() {
    slint_build::compile("ui/app.slint")
        .expect("Failed to compile Slint UI");
}