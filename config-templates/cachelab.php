<?php
require "staff.php";
if ($isstaff) {
    $staff_0_or_1 = "1";
} else {
    $staff_0_or_1 = "0";
}
$the_info = '{"username":"'.$user.'","timestamp":' . time() . ',"staff":'. $staff_0_or_1 . '}';
$key = 'XXX';
$the_hash = hash_hmac('sha512', $the_info, $key);
?>
<form action="https://archimedes.cs.virginia.edu:3331/login-setup" method="post" id="main">
    <input type="hidden" name="info" value="<?php echo htmlspecialchars($the_info) ?>">
    <input type="hidden" name="mac" value="<?php echo htmlspecialchars($the_hash) ?>">
    <input type="submit" name="continue">
</form>
<script>document.forms["main"].submit()</script>
