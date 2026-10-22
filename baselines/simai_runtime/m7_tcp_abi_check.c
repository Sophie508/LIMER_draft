#include <stdio.h>
#include <stddef.h>
#include <linux/tcp.h>
int main(){
printf("tcpi_unacked %zu\n", offsetof(struct tcp_info,tcpi_unacked));
printf("tcpi_lost %zu\n", offsetof(struct tcp_info,tcpi_lost));
printf("tcpi_retrans %zu\n", offsetof(struct tcp_info,tcpi_retrans));
printf("tcpi_rtt %zu\n", offsetof(struct tcp_info,tcpi_rtt));
printf("tcpi_total_retrans %zu\n", offsetof(struct tcp_info,tcpi_total_retrans));
printf("tcpi_bytes_acked %zu\n", offsetof(struct tcp_info,tcpi_bytes_acked));
printf("tcpi_bytes_sent %zu\n", offsetof(struct tcp_info,tcpi_bytes_sent));
printf("tcpi_dsack_dups %zu\n", offsetof(struct tcp_info,tcpi_dsack_dups));
printf("tcpi_reord_seen %zu\n", offsetof(struct tcp_info,tcpi_reord_seen));
}
